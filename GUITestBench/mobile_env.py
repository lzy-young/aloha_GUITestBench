#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import uuid
import random
import subprocess

from android_world.env import adb_utils
from android_world.utils import file_utils
from android_world.env import env_launcher
from android_world.utils import app_snapshot
from android_world.env import device_constants
from android_world.env.json_action import JSONAction
from android_world.env.actuation import execute_adb_action
from android_world.env.adb_utils import issue_generic_request
from android_world.task_evals.utils import sqlite_schema_utils
from android_world.agents.seeact_utils import format_and_filter_elements

from core.data_model import EnvParams
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from GUITestBench.constant import APK2PATH, APP2PACKAGE, ACTIVITY_MAP, DB_PATH

os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GRPC_TRACE'] = 'none'
os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '1'

APP_NAMES = list(ACTIVITY_MAP.keys())

# Level 1: BaseEnvironment class
class BaseEnviron:
    
    def __init__(
        self, 
        console_port: int, 
        grpc_port: int,
        adb_path: Optional[str] = None
    ):
        self.console_port = console_port
        self.grpc_port = grpc_port
        self.adb_path = adb_path
        self.init_env()
    
    def init_env(self) -> None:
        self.env = env_launcher.load_and_setup_env(
            console_port=self.console_port,
            adb_path=self.adb_path,
            grpc_port=self.grpc_port
        )
        print(f"✅ Environment initialized")
    
    def reset(self, go_home: bool = True) -> None:
        self.env.reset(go_home=go_home)
    
    def _get_state(self, wait_to_stabilize=True):
        return self.env.get_state(wait_to_stabilize=wait_to_stabilize)

    def _get_params(self) -> EnvParams:        
        return EnvParams(
            logical_screen_size=self.env.logical_screen_size,
            physical_frame_boundary=self.env.physical_frame_boundary,
            orientation=self.env.orientation
        )
    
    def _get_controller(self):
        return self.env.controller
    
    def __del__(self):
        try:
            if hasattr(self, 'env') and self.env is not None:
                # Check if env and its close method exist before calling
                if hasattr(self.env, 'close') and callable(getattr(self.env, 'close')):
                    try:
                        self.env.close()
                    except:
                        pass  # Ignore errors during cleanup in destructor
                self.env = None
        except:
            pass  # Suppress any errors during destruction
        
    def close(self):
        if hasattr(self, 'env') and self.env is not None:
            try:
                if hasattr(self.env, 'close') and callable(getattr(self.env, 'close')):
                    self.env.close()
                print("✅ Environment closed successfully")
            except Exception as e:
                print(f"⚠️ Error occurred while closing environment: {e}")
            finally:
                self.env = None

# Level 2: Functionalities class
class AppInstallerMixin:

    _apk2path = None
    _app2package = None
    
    @classmethod
    def _load_constants(cls):
        if cls._apk2path is None:
            cls._apk2path = APK2PATH
            cls._app2package = APP2PACKAGE

    def __init__(self, env):
        self._controller = env.controller
        self._load_constants()
    
    def find_apk_path(self, app_name: str) -> Optional[str]:
        return self._apk2path.get(app_name.lower())
    
    def get_package_name(self, app_name: str) -> Optional[str]:
        return self._app2package.get(app_name.lower())

    def get_all_app_versions(self, app_name: str) -> List[str]:
        target_package = self.get_package_name(app_name)
        if not target_package:
            return []
        
        versions = []
        for apk_name, package in self._app2package.items():
            if package == target_package and apk_name != app_name.lower():
                versions.append(apk_name)
        
        return versions

    def is_app_installed(self, package_name: str) -> bool:
        try:
            response = adb_utils.issue_generic_request(
                ['shell', 'pm', 'list', 'packages', package_name], 
                self._controller
            )
            output = response.generic.output.decode('utf-8')
            return package_name in output
        except Exception as e:
            print(f"❌ Error checking if {package_name} is installed: {e}")
            return False
    
    def install_apk(self, app_name: str) -> bool:
        apk_path = self.find_apk_path(app_name)
        if not apk_path:
            print(f"❌ APK file not found for: {app_name}")
            return False
        
        try:
            adb_utils.install_apk(apk_path, self._controller)
            print(f"✅ {app_name} installed successfully")
            return True
        except Exception as e:
            print(f"❌ {app_name} installation failed: {e}")
            return False
    
    def uninstall_app(self, package_name: str) -> bool:
        try:
            print(f"🗑️ Uninstalling {package_name}...")
            
            # force to stop the app
            adb_utils.issue_generic_request(
                ['shell', 'am', 'force-stop', package_name], 
                self._controller
            )
            time.sleep(2)
            
            # uninstall the app
            response = adb_utils.issue_generic_request(
                ['shell', 'pm', 'uninstall', package_name], 
                self._controller
            )
            
            output = response.generic.output.decode('utf-8')
            if response.status == 0 or 'Success' in output:
                print(f"✅ {package_name} uninstalled")
                return True
            elif "Unknown package:" in output:
                print(f"⚠️ {package_name} was not installed")
                return True
            else:
                print(f"❌ Uninstall {package_name} failed: {output}")
                return False
                
        except Exception as e:
            print(f"❌ Uninstall failed: {e}")
            return False
    
    def install_with_conflict_handling(self, app_name: str) -> bool:
        app_name = app_name.lower()
        package_name = self.get_package_name(app_name)
        
        if not package_name:
            print(f"❌ Package name not found for: {app_name}")
            return False
        
        
        conflict_versions = self.get_all_app_versions(app_name)
        if conflict_versions:
            print(f"🔍 Found conflict versions: {conflict_versions}")
        
        
        for conflict_app in conflict_versions:
            conflict_package = self.get_package_name(conflict_app)
            if conflict_package and self.is_app_installed(conflict_package):
                print(f"🗑️ Removing conflict version: {conflict_app}")
                self.uninstall_app(conflict_package)
        
        
        return self.install_apk(app_name)
    
class PermissionHandlerMixin:
    
    PERMISSION_ACTIONS: Dict[str, List[dict]] = {
        'owntracks': [
            {'action_type': 'click', 'x': 549, 'y': 2138},     # click 'Next' button
            {'action_type': 'click', 'x': 549, 'y': 2138},     # click 'Next' button
            {'action_type': 'click', 'x': 549, 'y': 2008},     # click 'REQUEAST' button
            {'action_type': 'click', 'x': 549, 'y': 1500},     # click 'While using the app' button
            {'action_type': 'click', 'x': 549, 'y': 2138},     # click 'Next' button
            {'action_type': 'click', 'x': 549, 'y': 2008},     # click 'REQUEAST' button
            {'action_type': 'click', 'x': 549, 'y': 1300},     # click 'Allow' button
            {'action_type': 'click', 'x': 549, 'y': 2138},     # click 'Next' button
            {'action_type': 'click', 'x': 549, 'y': 2138},     # click 'DONE' button
        ],
        'ankidroid-2_14': [
            {'action_type': 'click', 'x': 549, 'y': 1314},     # click 'Allow' button
            {'action_type': 'click', 'x': 878, 'y': 1693},     # click 'ok' button
            {'action_type': 'click', 'x': 549, 'y': 1336},     # click 'Allow' button
        ],
        'ankidroid-2_15': [
            {'action_type': 'click', 'x': 549, 'y': 1314},     # click 'Allow' button
            {'action_type': 'click', 'x': 878, 'y': 1693},     # click 'ok' button
            {'action_type': 'click', 'x': 549, 'y': 1336},     # click 'Allow' button
        ],
        'ankidroid-2_13_5': [
            {'action_type': 'click', 'x': 549, 'y': 1314},     # click 'Allow' button
            {'action_type': 'click', 'x': 878, 'y': 1693},     # click 'ok' button
            {'action_type': 'click', 'x': 549, 'y': 1336},     # click 'Allow' button
        ],
        'ankidroid-2_8_2': [
            {'action_type': 'click', 'x': 549, 'y': 1338},     # click 'Allow' button
        ],
        'amaze-3_4_3': [
            {'action_type': 'click', 'x': 549, 'y': 1332},     # click 'ALLOW' button
        ],
        'amaze-3_5_3': [
            {'action_type': 'click', 'x': 549, 'y': 1332},     # click 'ALLOW' button
        ],
        'androbd': [
            {'action_type': 'click', 'x': 549, 'y': 1332},     # click 'ALLOW' button
        ],
        'newpipe': [
            {'action_type': 'click', 'x': 549, 'y': 1332},     # click 'ALLOW' button
        ],
        'vibeyou': [
            {'action_type': 'click', 'x': 549, 'y': 1305},     # click 'ALLOW' button
        ],
        'opentracks-03': [
            {'action_type': 'click', 'x': 943, 'y': 2018},     # click 'Start' button
            {'action_type': 'click', 'x': 943, 'y': 2018},     # click 'Start' button
            {'action_type': 'click', 'x': 549, 'y': 1500},     # click 'While using the app' button
            {'action_type': 'click', 'x': 549, 'y': 1339},     # click 'Allow' button
            {'action_type': 'click', 'x': 549, 'y': 1308},     # click 'Allow' button
        ],
        'opentracks-4_12-4': [
            {'action_type': 'click', 'x': 943, 'y': 2018},     # click 'Start' button
            {'action_type': 'click', 'x': 943, 'y': 2018},     # click 'Start' button
            {'action_type': 'click', 'x': 549, 'y': 1500},     # click 'While using the app' button
            {'action_type': 'click', 'x': 549, 'y': 1339},     # click 'Allow' button
            {'action_type': 'click', 'x': 549, 'y': 1308},     # click 'Allow' button
        ],
        'opentracks-3_7_3': [
            {'action_type': 'click', 'x': 549, 'y': 1231},     # click 'While using the app' button
        ],
        'markor': [
            {'action_type': 'click', 'x': 895, 'y': 2216},     # click 'ok' button
            {'action_type': 'click', 'x': 922, 'y': 2096},     # click 'add' button
            {'action_type': 'click', 'x': 893, 'y': 1312},     # click 'ok' button
            {'action_type': 'click', 'x': 541, 'y': 1330},     # click 'Allow' button
        ],
    }
    
    def __init__(self, env):
        self._env = env
    
    def get_permission_actions(self, app_name: str) -> List[dict]:
        return self.PERMISSION_ACTIONS.get(app_name.lower(), [])
    
    def execute_ui_actions(self, action_dicts: List[dict]) -> bool:
        try:
            for index, action_dict in enumerate(action_dicts):
                action = JSONAction(**action_dict)
                state = self._env.get_state(wait_to_stabilize=True)
                text_desc = format_and_filter_elements(state.ui_elements)
                
                execute_adb_action(
                    action=action, 
                    screen_elements=[e.ui_element for e in text_desc], 
                    screen_size=self._env.logical_screen_size,
                    env=self._env.controller
                )
                time.sleep(1)
                print(f"✅ Action {index + 1}/{len(action_dicts)} executed")
            
            return True
            
        except Exception as e:
            print(f"❌ UI action failed: {e}")
            return False
    
    def handle_permission(self, app_name: str) -> bool:
        actions = self.get_permission_actions(app_name)
        
        if not actions:
            print(f"📢 No permission actions defined for: {app_name}")
            return True
        
        print(f"🔐 Handling permissions for {app_name} ({len(actions)} actions)")
        return self.execute_ui_actions(actions)
    
class DatabaseHandlerMixin:
    
    def __init__(self, env):
        self._env = env

    
    def create_broccoli_database(self, app_name="broccoli", recipes_data=[]) -> bool:

        db_path = DB_PATH.get(app_name.lower(), '')
        
        try:
            clear_cmd = f"sqlite3 {db_path} \"DELETE FROM recipes; VACUUM;\""
            adb_utils.issue_generic_request(["shell", clear_cmd], self._env.controller)
            print("✅ Clear the existing recipes")
            
            # Adding new recipes
            for recipe_data in recipes_data:
                title       = recipe_data.get('title', 'Untitled Recipe').replace("'", "''")
                description = recipe_data.get('description', '').replace("'", "''")
                servings    = recipe_data.get('servings', '').replace("'", "''")
                prep_time   = recipe_data.get('preparationTime', '').replace("'", "''")
                source      = recipe_data.get('source', '').replace("'", "''")
                ingredients = recipe_data.get('ingredients', '').replace("'", "''")
                directions  = recipe_data.get('directions', '').replace("'", "''")
                favorite    = recipe_data.get('favorite', 0)
                image_name  = recipe_data.get('imageName', '').replace("'", "''")
                
                try:
                    insert_sql = (
                        f"INSERT INTO recipes (title, description, servings, preparationTime, source, ingredients, directions, favorite, imageName) "
                        f"VALUES ('{title}', '{description}', '{servings}', '{prep_time}', '{source}', '{ingredients}', '{directions}', {favorite}, '{image_name}');"
                    )
                    sql_cmd = f"sqlite3 {db_path} \"{insert_sql}\""
                    adb_utils.issue_generic_request(["shell", sql_cmd], self._env.controller)
                except:
                    basic_insert_sql = (
                        f"INSERT INTO recipes (title, directions, favorite) "
                        f"VALUES ('{title}', '{directions}', {favorite});"
                    )
                    sql_cmd = f"sqlite3 {db_path} \"{basic_insert_sql}\""
                    adb_utils.issue_generic_request(["shell", sql_cmd], self._env.controller)
                
            print(f"✅ Successfully added {len(recipes_data)} recipes")

            return True

        except Exception as e:
            print(f"❌ Failed to create {app_name} recipes and snapshot: {e}")
            return False
    
    
    def create_tasks_database(self, app_name='tasks', tasks_data = []) -> bool:        
        
        db_path = DB_PATH.get(app_name.lower(), '')
        
        try:
            clear_cmd = f"sqlite3 {db_path} \"DELETE FROM tasks; VACUUM;\""
            adb_utils.issue_generic_request(["shell", clear_cmd], self._env.controller)
            adb_utils.close_app(app_name, self._env.controller)  # Register changes
            print("✅ Clear existing tasks")
            
            tasks = []
            for task_data in tasks_data:
                due_date_ts = 0
                completed_ts = 0
                
                if task_data.get('due_date'):
                    due_datetime = datetime.strptime(task_data['due_date'], '%Y-%m-%d %H:%M:%S')
                    due_date_ts = int(due_datetime.timestamp() * 1000)
                
                if task_data.get('completed', False):
                    completed_datetime = datetime.now() - timedelta(days=random.randint(1, 7))
                    completed_ts = int(completed_datetime.timestamp() * 1000)
                
                
                created_date_ts = due_date_ts - (7 * 24 * 3600 * 1000) if due_date_ts > 0 else int(datetime.now().timestamp() * 1000)
                
                task = sqlite_schema_utils.Task(
                    title=task_data.get('title', 'Untitled Task'),
                    notes=task_data.get('notes'),
                    importance=task_data.get('importance', 2),
                    dueDate=due_date_ts,
                    completed=completed_ts,
                    created=created_date_ts,
                    modified=created_date_ts,
                    remoteId=str(uuid.uuid4().int),
                    recurrence=None,
                    hideUntil=0
                )
                tasks.append(task)
            
            # Insert tasks into the database
            from android_world.task_evals.utils import sqlite_utils
            sqlite_utils.insert_rows_to_remote_db(
                tasks,
                '_id',
                'tasks',
                db_path,
                app_name,
                self._env
            )
            
            adb_utils.close_app(app_name, self._env.controller)  # Register changes
            print(f"✅ Successfully added {len(tasks)} tasks")
            return True
            
        except Exception as e:
            print(f"❌ Operation failed: {e}")
            return False
    
    
    def create_owntracks_database(self, app_name='owntracks', waypoints_data=[]) -> bool:
        
        db_path = DB_PATH.get(app_name.lower(), '')
        
        try:
            adb_utils.issue_generic_request(["shell", "am start -n org.owntracks.android/.ui.map.MapActivity"], self._env.controller)
            print("✅ Loaded OwnTracks app to initialize database")

            try:
                schema_cmd = f"sqlite3 {db_path} \".schema\""
                schema_result = adb_utils.issue_generic_request(["shell", schema_cmd], self._env.controller)
                if hasattr(schema_result, 'generic') and hasattr(schema_result.generic, 'output'):
                    schema_output = schema_result.generic.output if schema_result.generic.output else b""
                else:
                    schema_output = schema_result if schema_result else b""
                if isinstance(schema_output, bytes):
                    schema_output = schema_output.decode('utf-8', errors='ignore')
                elif isinstance(schema_output, str):
                    schema_output = schema_output
                else:
                    schema_output = str(schema_output)
                print(f"Database Mode: {schema_output}")
            
            except Exception as schema_error:
                print(f"Get database schema failed: {schema_error}")
                schema_output = ""
            
            try:
                tables_cmd = f"sqlite3 {db_path} \".tables\""
                tables_result = adb_utils.issue_generic_request(["shell", tables_cmd], self._env.controller)
                if hasattr(tables_result, 'generic') and hasattr(tables_result.generic, 'output'):
                    tables_output = tables_result.generic.output if tables_result.generic.output else b""
                else:
                    tables_output = tables_result if tables_result else b""
                
                if isinstance(tables_output, bytes):
                    tables_output = tables_output.decode('utf-8', errors='ignore')
                elif isinstance(tables_output, str):
                    tables_output = tables_output
                else:
                    tables_output = str(tables_output)
                    
                print(f"Database Tables: {tables_output}")
            
            except Exception as tables_error:
                print(f"Get database table info failed: {tables_error}")
                tables_output = ""
            
            if "WaypointModel" in tables_output:
                clear_cmd = f"sqlite3 {db_path} \"DELETE FROM WaypointModel; VACUUM;\""
                adb_utils.issue_generic_request(["shell", clear_cmd], self._env.controller)
                print("✅ Cleared existing waypoints")
                
                for location_data in waypoints_data:
                    latitude = location_data.get('latitude', 0.0)
                    longitude = location_data.get('longitude', 0.0)
                    accuracy = location_data.get('accuracy', 20)  # geofenceRadius对应accuracy
                    description = location_data.get('description', 'Test Location')
                    timestamp = location_data.get('timestamp', int(time.time()))
                    
                    try:
                        insert_sql = (
                            f"INSERT INTO WaypointModel (description, geofenceLatitude, geofenceLongitude, geofenceRadius, lastTriggered, lastTransition, tst) "
                            f"VALUES ('{description}', {latitude}, {longitude}, {accuracy}, NULL, 0, {timestamp});"
                        )
                        sql_cmd = f"sqlite3 {db_path} \"{insert_sql}\""
                        adb_utils.issue_generic_request(["shell", sql_cmd], self._env.controller)
                    except Exception as insert_error:
                        try:
                            basic_insert_sql = (
                                f"INSERT INTO WaypointModel (description, geofenceLatitude, geofenceLongitude, geofenceRadius, lastTransition, tst) "
                                f"VALUES ('Location', {latitude}, {longitude}, 20, 0, {timestamp});"
                            )
                            sql_cmd = f"sqlite3 {db_path} \"{basic_insert_sql}\""
                            adb_utils.issue_generic_request(["shell", sql_cmd], self._env.controller)
                            print(f"⚠️ Location ({latitude}, {longitude}) failed, using basic insert: {insert_error}")
                        except Exception as basic_insert_error:
                            print(f"❌ Location ({latitude}, {longitude}) failed, basic insert also failed: {basic_insert_error}")
            
            else:
                print("❌ Failed to find WaypointModel table in OwnTracks database, OwnTracks database structure may be incorrect")
                return False
        
            print(f"✅ Successfully added {len(waypoints_data)} waypoints")            
            return True

        except Exception as e:
            print(f"❌ Operation failed: {e}")
            return False

    
    def create_catima_database(self, app_name='catima', local_catima_file: str = 'catima.zip') -> bool:
        print(f"📤 Push {local_catima_file} to Android device...")
        push_command = ['push', local_catima_file, '/sdcard/Download/']
        try:
            response = issue_generic_request(push_command, self._env.controller)
            
            output = response.generic.output.decode('utf-8') if response.generic.output else ""
            if response.status == 0 or "file pushed" in output:
                print("✅ File push successful")
            else:
                print(f"❌ File push failed: {output}")
                raise RuntimeError(f"Failed to push file to emulator: {output}")
        except Exception as e:
            print(f"❌ Error in file push: {e}")
            raise
        
        try:
            action_dicts = [
                {'action_type': 'open_app', 'app_name': app_name}, 
                {'action_type': 'click', 'x': 1023, 'y': 213},     # click 'more options' button
                {'action_type': 'click', 'x': 1027, 'y': 300},     # click 'Import/Export' button
                {'action_type': 'click', 'x': 538, 'y': 1187},     # click 'From filesystem' button
                {'action_type': 'click', 'x': 223, 'y': 1070},     # click 'Catima' button
                {'action_type': 'click', 'x': 840, 'y': 1454},     # click 'OK' button
                {'action_type': 'click', 'x': 73, 'y': 195},       # click 'Open from' button
                {'action_type': 'click', 'x': 313, 'y': 646},      # click 'Download' button
                {'action_type': 'click', 'x': 313, 'y': 760},      # click 'catima.zip' button
                {'action_type': 'click', 'x': 243, 'y': 1382},     # click 'OK' button
                {'action_type': 'click', 'x': 73, 'y': 213},       # click 'Back' button
                {'action_type': 'click', 'x': 789, 'y': 207},      # click 'Display Option' button
                {'action_type': 'click', 'x': 186, 'y': 1217},     # click 'Show balance' button
                {'action_type': 'click', 'x': 186, 'y': 1340},     # click 'Show validity' button
                {'action_type': 'click', 'x': 835, 'y': 1637},     # click 'OK' button
            ]
            
            for index, action_dict in enumerate(action_dicts):
                action = JSONAction(**action_dict)
                state = self._env.get_state(wait_to_stabilize=True)
                text_desc = format_and_filter_elements(state.ui_elements)
                
                try:
                    execute_adb_action(
                        action=action, 
                        screen_elements=[e.ui_element for e in text_desc], 
                        screen_size=self._env.logical_screen_size,
                        env=self._env.controller
                    )
                    print(f"✅ Action {index} executed successfully: {action_dict}")
                except Exception as e:
                    print(f"❌ Execute action `{action}` failed at index {index}: {e}")
                    raise ValueError(f'Execute action `{action}` failed: {e}')
            
            print(f"✅ Successfully added Catima cards from {local_catima_file}")
            return True
            
        except Exception as e:
            print(f"❌ Operation failed: {e}")
            return False

    
    def create_ankidroid_database(self, app_name='ankidroid-2_14', notes_data=[]) -> bool:
                
        db_path = DB_PATH.get(app_name.lower(), '')
        
        try:
            print("=" * 60)
            print("🚀 AnkiDroid Database Initialization")
            print("=" * 60)
            
            
            print("\n[Step 1/5] Starting AnkiDroid to initialize database...")
            adb_utils.issue_generic_request(
                ["shell", "am", "start", "-n", "com.ichi2.anki/.IntentHandler"], 
                self._env.controller
            )
            time.sleep(10)
            
            
            print("\n[Step 2/5] Checking database existence...")
            check_db_cmd = f"test -f {db_path} && echo 'exists' || echo 'not exists'"
            response = adb_utils.issue_generic_request(
                ["shell", check_db_cmd], 
                self._env.controller
            )
            db_status = response.generic.output.decode('utf-8').strip()
            
            if 'not exists' in db_status:
                print(f"❌ AnkiDroid database not found at {db_path}")
                return False
            
            print(f"✅ AnkiDroid database found")
            
            
            print("\n[Step 3/5] Closing app to safely access database...")
            adb_utils.close_app('ankidroid-2_14', self._env.controller)
            time.sleep(2)
            
            
            print("\n[Step 4/5] Retrieving model ID...")
            
            
            get_mid_cmd = f"sqlite3 {db_path} \"SELECT mid FROM notes LIMIT 1;\""
            response = adb_utils.issue_generic_request(
                ["shell", get_mid_cmd], 
                self._env.controller
            )
            mid_output = response.generic.output.decode('utf-8', errors='ignore').strip()
            
            model_id = None
            if mid_output and mid_output.isdigit():
                model_id = mid_output
                print(f"✅ Found model ID from existing notes: {model_id}")
            else:
                
                print("   No existing notes found, extracting from models field...")
                
                get_model_cmd = f"sqlite3 {db_path} \"SELECT models FROM col;\""
                response = adb_utils.issue_generic_request(
                    ["shell", get_model_cmd], 
                    self._env.controller
                )
                models_json = response.generic.output.decode('utf-8', errors='ignore').strip()
                
                if not models_json:
                    print("❌ Models field is empty!")
                    return False
                
                import re
                
                model_ids = re.findall(r'"(\d{13})":', models_json)
                
                if not model_ids:
                    
                    model_ids = re.findall(r'"(\d{10,})":', models_json)
                
                if not model_ids:
                    print("❌ Failed to extract model ID")
                    print(f"   Models data (first 200 chars): {models_json[:200]}")
                    return False
                
                model_id = model_ids[0]
                print(f"✅ Found model ID from models field: {model_id}")
            
            
            print(f"\n[Step 5/5] Inserting {len(notes_data)} cards...")
            
            success_count = 0
            for idx, card_data in enumerate(notes_data, 1):
                try:
                    front = card_data.get('front', '').replace("'", "''")
                    back = card_data.get('back', '').replace("'", "''")
                    tags = card_data.get('tags', '').replace("'", "''")
                    
                    if not front:
                        print(f"⚠️  Skipping card {idx}: front field is empty")
                        continue
                    
                    
                    note_id = int(time.time() * 1000) + idx
                    card_id = note_id + 1
                    current_time = int(time.time())
                    guid = f"anki{note_id}"
                    
                    
                    insert_note_sql = f"""
                    INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
                    VALUES (
                        {note_id}, 
                        '{guid}', 
                        {model_id}, 
                        {current_time}, 
                        -1, 
                        '{tags}', 
                        '{front}' || char(31) || '{back}', 
                        0, 
                        0, 
                        0, 
                        ''
                    );
                    """
                    
                    sql_cmd = f'sqlite3 {db_path} "{insert_note_sql}"'
                    response = adb_utils.issue_generic_request(
                        ["shell", sql_cmd], 
                        self._env.controller
                    )
                    
                    
                    get_max_due_cmd = f"sqlite3 {db_path} \"SELECT MAX(due) FROM cards WHERE queue = 0;\""
                    response = adb_utils.issue_generic_request(
                        ["shell", get_max_due_cmd], 
                        self._env.controller
                    )
                    max_due_str = response.generic.output.decode('utf-8', errors='ignore').strip()
                    due = int(max_due_str) + 1 if max_due_str and max_due_str.isdigit() else idx
                    
                    
                    insert_card_sql = f"""
                    INSERT INTO cards (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)
                    VALUES (
                        {card_id}, 
                        {note_id}, 
                        1, 
                        0, 
                        {current_time}, 
                        -1, 
                        0, 
                        0, 
                        {due}, 
                        0, 
                        0, 
                        0, 
                        0, 
                        0, 
                        0, 
                        0, 
                        0, 
                        ''
                    );
                    """
                    
                    sql_cmd = f'sqlite3 {db_path} "{insert_card_sql}"'
                    response = adb_utils.issue_generic_request(
                        ["shell", sql_cmd], 
                        self._env.controller
                    )
                    
                    success_count += 1
                    print(f"   ✓ Card {idx}/{len(notes_data)}: {front[:30]}...")
                    
                    
                    time.sleep(0.01)
                    
                except Exception as e:
                    print(f"   ✗ Failed to insert card {idx}: {e}")
                    continue
            
            print(f"✅ Successfully added {success_count}/{len(notes_data)} cards")    
            return True
            
        except Exception as e:
            print(f"\n❌ Failed to create AnkiDroid cards: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_markor_and_database(self, app_name='markor', notes_data=[]) -> bool:
        try:
            # Clear the existing Markor Notes
            file_utils.clear_directory(
                device_constants.MARKOR_DATA, 
                self._env.controller
            )
            for note_data in notes_data:
                filename = note_data.get('name', f"note_{len(notes_data)}.md")
                content = note_data.get('content', 'Empty note')
                
                file_utils.create_file(
                    filename,
                    device_constants.MARKOR_DATA, 
                    self._env.controller,
                    content
                )
            print(f"✅ Successfully added {len(notes_data)} notes")
            return True

        except Exception as e:
            print(f"❌ Failed to create the {app_name} notes: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def setup_precondition(self, app_name: str, condition: Any = None) -> bool:
        app_name = app_name.lower()
        
        if app_name == 'broccoli':
            return self.create_broccoli_database(app_name, condition or [])
        elif app_name == 'tasks':
            return self.create_tasks_database(app_name, condition or [])
        elif app_name == 'owntracks':
            return self.create_owntracks_database(app_name, condition or [])
        elif app_name == 'catima':
            return self.create_catima_database(app_name, condition)
        elif app_name in ['ankidroid-2_14', 'ankidroid-2_15', 'ankidroid-2_13_5']:
            return self.create_ankidroid_database(app_name, condition or [])
        else:
            print(f"📢 No pre-condition defined for: {app_name}")
            return True

class SnapshotHandlerMixin:
    def __init__(self, env):
        self._env = env
    
    def save_snapshot(self, app_name: str):
        try:
            app_snapshot.save_snapshot(app_name, self._env.controller)
            print(f"✅ {app_name} snapshot created successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to create snapshot for {app_name}: {e}")
            return False

    def clear_snapshot(self, app_name: str):
        try:
            app_snapshot.clear_snapshot(app_name, self._env.controller)
            print(f"✅ {app_name} snapshot cleared successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to clear snapshot for {app_name}: {e}")
            return False
    
    def restore_snapshot(self, app_name: str):
        try:
            app_snapshot.restore_snapshot(app_name, self._env.controller)
            print(f"✅ {app_name} snapshot restored from existing snapshot")
            return True
        except RuntimeError:
            print(f"ℹ️  No existing snapshot found for {app_name}, creating from config...")
            return False

# Level 3: Mobile Base Environment
class MobileBaseEnv(BaseEnviron):
    def __init__(
        self, 
        console_port: int = 5556, 
        grpc_port: int = 8557, 
        adb_path: str = '/your/local/path/to/adb'
    ):
        super().__init__(console_port, grpc_port, adb_path)
        
        self._installer: Optional[AppInstallerMixin] = None
        self._permission_handler: Optional[PermissionHandlerMixin] = None
        self._database_handler: Optional[DatabaseHandlerMixin] = None
        self._snapshot_handler: Optional[SnapshotHandlerMixin] = None
    
    @property
    def installer(self) -> AppInstallerMixin:
        if self._installer is None:
            self._installer = AppInstallerMixin(self.env)
        return self._installer
    
    @property
    def permission_handler(self) -> PermissionHandlerMixin:
        if self._permission_handler is None:
            self._permission_handler = PermissionHandlerMixin(self.env)
        return self._permission_handler
    
    @property
    def snapshot_handler(self) -> SnapshotHandlerMixin:
        if self._snapshot_handler is None:
            self._snapshot_handler = SnapshotHandlerMixin(self.env)
        return self._snapshot_handler
    
    @property
    def database_handler(self) -> DatabaseHandlerMixin:
        if self._database_handler is None:
            self._database_handler = DatabaseHandlerMixin(self.env)
        return self._database_handler

    def close(self):
        # Clean up all mixin handlers first
        self._installer = None
        self._permission_handler = None
        self._database_handler = None
        self._snapshot_handler = None
        
        # Then close the base environment
        if hasattr(self, 'env') and self.env is not None:
            try:
                if hasattr(self.env, 'close') and callable(getattr(self.env, 'close')):
                    self.env.close()
                print("✅ Environment closed successfully")
            except Exception as e:
                print(f"⚠️ Error occurred while closing environment: {e}")
            finally:
                self.env = None

    def install_app(self, app_name: str) -> bool:
        print(f"\n📦 Installing {app_name}...")
        return self.installer.install_with_conflict_handling(app_name)
    
    def uninstall_app(self, app_name: str) -> bool:
        package_name = self.installer.get_package_name(app_name)
        if not package_name:
            print(f"❌ Package not found for: {app_name}")
            return False
        return self.installer.uninstall_app(package_name)
    
    def open_app(self, app_name: str) -> None:
        print(f"\n🚀 Opening {app_name}...")
        
        activity = ACTIVITY_MAP.get(app_name)
        if not activity:
            raise ValueError(f"No activity found for: {app_name}")
        
        adb_path_expanded = os.path.expanduser(self.adb_path)
        emulator_id = f"emulator-{self.console_port}"
        
        
        subprocess.run(
            [adb_path_expanded, "-s", emulator_id, "root"], 
            check=False,
            capture_output=True
        )
        
        
        subprocess.run(
            [adb_path_expanded, "-s", emulator_id, "shell", "am", "start", "-n", activity],
            check=False,
            capture_output=True
        )
        
        time.sleep(2)
        print(f"✅ {app_name} opened")
    
    def request_permission(self, app_name: str) -> bool:
        print(f"\n🔐 Requesting permissions for {app_name}...")
        return self.permission_handler.handle_permission(app_name)
    
    def setup_precondition(self, app_name: str, condition: Any = None) -> bool:
        print(f"\n📋 Setting up precondition for {app_name}...")
        return self.database_handler.setup_precondition(app_name, condition)
    
    def save_snapshot(self, app_name: str) -> bool:
        return self.snapshot_handler.save_snapshot(app_name)
    
    def clear_snapshot(self, app_name: str) -> bool:
        return self.snapshot_handler.clear_snapshot(app_name)
    
    def restore_snapshot(self, app_name: str) -> bool:
        return self.snapshot_handler.restore_snapshot(app_name)

    def get_state(self, wait_to_stabilize=True):
        return self._get_state(wait_to_stabilize=wait_to_stabilize)
    
    def get_params(self) -> EnvParams:
        return self._get_params()
    