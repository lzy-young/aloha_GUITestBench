#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import json

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any
from GUITestBench.mobile_env import MobileBaseEnv
from GUITestBench.app_registry import AppType, registry
from android_world.env.actuation import execute_adb_action


@dataclass
class AppState:
    
    app_name: str
    is_installed: bool = False
    has_snapshot: bool = False
    is_configured: bool = False


class AppEnvironmentManager(MobileBaseEnv):
    
    
    def __init__(
        self,
        console_port: int = 5556,
        grpc_port: int = 8557,
        adb_path: str = '/your/local/path/to/adb',
        state_file: str = './GUITestBench/app_states.json'
    ):
        super().__init__(console_port, grpc_port, adb_path)
        
        self.registry = registry
        self.state_file = Path(state_file)
        self._app_states: Dict[str, AppState] = {}
        self._current_multi_version_apps: Dict[str, str] = {}  # base_name -> current_version
        
        self._load_states()
    
    
    
    def _load_states(self):
        
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    for name, state in data.get('app_states', {}).items():
                        self._app_states[name] = AppState(**state)
                    self._current_multi_version_apps = data.get('multi_version_current', {})
            except Exception as e:
                print(f"⚠️ Failed to load states: {e}")
    
    def _save_states(self):
        
        try:
            data = {
                'app_states': {
                    name: {
                        'app_name': state.app_name,
                        'is_installed': state.is_installed,
                        'has_snapshot': state.has_snapshot,
                        'is_configured': state.is_configured
                    }
                    for name, state in self._app_states.items()
                },
                'multi_version_current': self._current_multi_version_apps
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save states: {e}")
    
    def _get_app_state(self, app_name: str) -> AppState:
        
        if app_name not in self._app_states:
            self._app_states[app_name] = AppState(app_name=app_name)
        return self._app_states[app_name]
    
    def _update_app_state(self, app_name: str, **kwargs):
        
        state = self._get_app_state(app_name)
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        self._save_states()
    
    
    
    def prepare_environment(
        self,
        app_name: str,
        db_data: Any = None,
        force_reinstall: bool = False
    ) -> bool:
        
        app_info = self.registry.get_app(app_name)
        if not app_info:
            print(f"❌ Unknown app: {app_name}")
            return False
        
        print(f"\n{'='*50}")
        print(f"📱 Preparing environment for: {app_name}")
        print(f"   Type: {app_info.app_type.value}")
        print(f"{'='*50}")
        
        if app_info.app_type == AppType.SINGLE_VERSION:
            return self._prepare_single_version_app(app_name, db_data, force_reinstall)
        else:
            return self._prepare_multi_version_app(app_name, db_data, force_reinstall)
    
    def _prepare_single_version_app(
        self,
        app_name: str,
        db_data: Any = None,
        force_reinstall: bool = False
    ) -> bool:
        
        state = self._get_app_state(app_name)
        
        
        if state.has_snapshot and not force_reinstall:
            print(f"📸 Restoring snapshot for {app_name}...")
            if self.restore_snapshot(app_name):
                print(f"✅ Environment ready (from snapshot)")
                return True
            else:
                print(f"⚠️ Snapshot restore failed, will reinstall")
        
        
        return self._full_install_and_setup(app_name, db_data)
    
    def _prepare_multi_version_app(
        self,
        app_name: str,
        db_data: Any = None,
        force_reinstall: bool = False
    ) -> bool:
        
        app_info = self.registry.get_app(app_name)
        base_name = app_info.base_name
        
        current_installed = self._current_multi_version_apps.get(base_name)
        
        
        if current_installed and current_installed != app_name:
            print(f"🔄 Version switch required: {current_installed} -> {app_name}")
            self._cleanup_multi_version_app(current_installed)
        elif current_installed == app_name and not force_reinstall:
            
            state = self._get_app_state(app_name)
            if state.has_snapshot:
                print(f"📸 Restoring snapshot for {app_name}...")
                if self.restore_snapshot(app_name):
                    print(f"✅ Environment ready (from snapshot)")
                    return True
        
        
        success = self._full_install_and_setup(app_name, db_data)
        if success:
            self._current_multi_version_apps[base_name] = app_name
            self._save_states()
        
        return success
    
    def _cleanup_multi_version_app(self, app_name: str) -> bool:
        
        print(f"\n🗑️ Cleaning up {app_name}...")
        
        app_info = self.registry.get_app(app_name)
        if not app_info:
            return False
        
        
        self.clear_snapshot(app_name)
        
        
        self.uninstall_app(app_name)
        
        
        self._update_app_state(
            app_name,
            is_installed=False,
            has_snapshot=False,
            is_configured=False
        )
        
        return True
    
    def _full_install_and_setup(
        self,
        app_name: str,
        db_data: Any = None
    ) -> bool:
        
        print(f"\n🔧 Starting full installation for {app_name}...")
        
        app_info = self.registry.get_app(app_name)
        
        
        print(f"\n[1/5] Installing APK...")
        if not self.install_app(app_name):
            print(f"❌ Installation failed")
            return False
        
        
        print(f"\n[2/5] Opening app...")
        try:
            self.open_app(app_name)
        except Exception as e:
            print(f"⚠️ Failed to open app: {e}")
        
        
        print(f"\n[3/5] Handling permissions...")
        if app_info.requires_permission:
            self.request_permission(app_name)
        
        
        print(f"\n[4/5] Setting up database...")
        if app_info.requires_database and db_data is not None:
            self.setup_precondition(app_name, db_data)
        
        
        print(f"\n[5/5] Creating snapshot...")
        snapshot_success = self.save_snapshot(app_name)
        
        
        self._update_app_state(
            app_name,
            is_installed=True,
            has_snapshot=snapshot_success,
            is_configured=True
        )
        
        print(f"\n✅ {app_name} environment ready!")
        return True
    
    
    
    def prepare_all_single_version_apps(self, db_configs: Dict[str, Any] = None) -> Dict[str, bool]:
        
        db_configs = db_configs or {}
        results = {}
        
        single_apps = self.registry.get_single_version_apps()
        print(f"\n{'='*60}")
        print(f"📦 Preparing {len(single_apps)} single-version apps...")
        print(f"{'='*60}")
        
        for app_name in single_apps:
            db_data = db_configs.get(app_name)
            results[app_name] = self.prepare_environment(app_name, db_data)
        
        
        success_count = sum(1 for v in results.values() if v)
        print(f"\n{'='*60}")
        print(f"📊 Summary: {success_count}/{len(results)} apps prepared successfully")
        print(f"{'='*60}")
        
        return results
    
    def cleanup_all_multi_version_apps(self) -> bool:
        
        print(f"\n🧹 Cleaning up all multi-version apps...")
        
        for base_name, current_version in list(self._current_multi_version_apps.items()):
            if current_version:
                self._cleanup_multi_version_app(current_version)
        
        self._current_multi_version_apps.clear()
        self._save_states()
        return True
    
    
    
    def get_current_installed_version(self, base_name: str) -> Optional[str]:
        
        return self._current_multi_version_apps.get(base_name)
    
    def is_app_ready(self, app_name: str) -> bool:
        
        state = self._get_app_state(app_name)
        return state.is_installed and state.is_configured
    
    def get_all_states(self) -> Dict[str, AppState]:
        
        return self._app_states.copy()
    
    def print_status(self):
        
        print(f"\n{'='*60}")
        print("📊 Current Environment Status")
        print(f"{'='*60}")
        
        print("\n🟢 Single-version apps:")
        for app_name in self.registry.get_single_version_apps():
            state = self._get_app_state(app_name)
            status = "✅ Ready" if state.is_configured else "⚪ Not configured"
            snapshot = "📸" if state.has_snapshot else "  "
            print(f"   {snapshot} {app_name}: {status}")
        
        print("\n🔄 Multi-version apps:")
        for base_name, versions in self.registry.MULTI_VERSION_GROUPS.items():
            current = self._current_multi_version_apps.get(base_name, "None")
            print(f"   {base_name}: current = {current}")
            for v in versions:
                state = self._get_app_state(v)
                marker = "►" if v == current else " "
                snapshot = "📸" if state.has_snapshot else "  "
                print(f"      {marker} {snapshot} {v}")
        
        print(f"{'='*60}\n")

    def execute_adb_action(self, action, observation):
        execute_adb_action(
            action=action, 
            screen_elements=[e.ui_element for e in observation.text_desc], 
            screen_size=self._get_params().logical_screen_size,
            env=self._get_controller()
        )
