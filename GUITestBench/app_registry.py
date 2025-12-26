#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from GUITestBench.constant import APK2PATH, APP2PACKAGE

class AppType(Enum):
    
    SINGLE_VERSION = "single"      
    MULTI_VERSION = "multi"        


@dataclass
class AppInfo:
    
    app_name: str                          
    apk_path: str                           
    package_name: str                       
    app_type: AppType                       
    base_name: str                          
    requires_permission: bool = True        
    requires_database: bool = False         
    default_db_data: Optional[dict] = None  


@dataclass
class VersionGroup:
    
    base_name: str                          
    versions: List[str] = field(default_factory=list)  
    current_installed: Optional[str] = None  

class AppRegistry:
    
    
    
    SINGLE_VERSION_APPS = {
        "newpipe", "faketraveler", "vibeyou", "broccoli", 
        "tasks", "catima", "markor", "owntracks", "androbd"
    }
    
    
    MULTI_VERSION_GROUPS = {
        "amaze": ["amaze-3_4_3", "amaze-3_5_3"],
        "opentracks": ["opentracks-03", "opentracks-3_7_3", "opentracks-4_12-4"],
        "ankidroid": ["ankidroid-2_8_2", "ankidroid-2_13_5", "ankidroid-2_14", "ankidroid-2_15"]
    }
    
    
    APPS_REQUIRING_DATABASE = {
        "broccoli", "tasks", "owntracks", "catima",
        "ankidroid-2_14", "ankidroid-2_15", "ankidroid-2_13_5", "markor"
    }
    
    def __init__(self):
        self._apps: Dict[str, AppInfo] = {}
        self._version_groups: Dict[str, VersionGroup] = {}
        self._initialize_registry()
    
    def _initialize_registry(self):
        
        for app_name in self.SINGLE_VERSION_APPS:
            self._register_app(
                app_name=app_name,
                app_type=AppType.SINGLE_VERSION,
                base_name=app_name
            )
        
        
        for base_name, versions in self.MULTI_VERSION_GROUPS.items():
            self._version_groups[base_name] = VersionGroup(
                base_name=base_name,
                versions=versions
            )
            for app_name in versions:
                self._register_app(
                    app_name=app_name,
                    app_type=AppType.MULTI_VERSION,
                    base_name=base_name
                )
    
    def _register_app(self, app_name: str, app_type: AppType, base_name: str):
        
        apk_path = APK2PATH.get(app_name)
        package_name = APP2PACKAGE.get(app_name)
        
        if not apk_path or not package_name:
            print(f"⚠️ Warning: Missing APK path or package name for {app_name}")
            return
        
        self._apps[app_name] = AppInfo(
            app_name=app_name,
            apk_path=apk_path,
            package_name=package_name,
            app_type=app_type,
            base_name=base_name,
            requires_database=app_name in self.APPS_REQUIRING_DATABASE
        )
    
    def get_app(self, app_name: str) -> Optional[AppInfo]:
        
        return self._apps.get(app_name.lower())
    
    def get_version_group(self, base_name: str) -> Optional[VersionGroup]:
        
        return self._version_groups.get(base_name.lower())
    
    def get_conflicting_versions(self, app_name: str) -> List[str]:
        
        app = self.get_app(app_name)
        if not app or app.app_type != AppType.MULTI_VERSION:
            return []
        
        group = self._version_groups.get(app.base_name)
        if not group:
            return []
        
        return [v for v in group.versions if v != app_name]
    
    def is_single_version(self, app_name: str) -> bool:
        
        app = self.get_app(app_name)
        return app is not None and app.app_type == AppType.SINGLE_VERSION
    
    def is_multi_version(self, app_name: str) -> bool:
        
        app = self.get_app(app_name)
        return app is not None and app.app_type == AppType.MULTI_VERSION
    
    def get_all_apps(self) -> List[str]:
        
        return list(self._apps.keys())
    
    def get_single_version_apps(self) -> List[str]:
        
        return [name for name, info in self._apps.items() 
                if info.app_type == AppType.SINGLE_VERSION]
    
    def get_multi_version_apps(self) -> List[str]:
        
        return [name for name, info in self._apps.items() 
                if info.app_type == AppType.MULTI_VERSION]



registry = AppRegistry()
