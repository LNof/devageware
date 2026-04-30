from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Platform:
    name: str
    vendor: str
    mcu: str
    toolchain: str  # "ncs", "mcuxpresso", "arduino", "platformio"
    language: str   # "c", "cpp"
    board: Optional[str] = None
    sdk_path: Optional[str] = None
    toolchain_path: Optional[str] = None


@dataclass
class FirmwareModule:
    name: str
    filename: str
    description: str
    code: str


@dataclass
class FirmwareProject:
    # project info
    name: str
    version: str = "0.1.0"
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    # platform
    platform: Optional[Platform] = None

    # source files
    modules: list[FirmwareModule] = field(default_factory=list)
    cmakelists: str = ""
    prj_conf: str = ""
    platformio_ini: str = ""
    linker_script: str = ""
    main_c: str = ""

    # build outputs
    bin_path: Optional[str] = None
    hex_path: Optional[str] = None
    build_log: Optional[str] = None
    build_success: bool = False

    # remote locations
    git_repo_url: Optional[str] = None
    nexus_artifact_url: Optional[str] = None
    notion_doc_url: Optional[str] = None

    def get_project_structure(self) -> dict:
        """Return the project file structure as a dict."""
        structure = {}

        if self.cmakelists:
            structure["CMakeLists.txt"] = self.cmakelists
        if self.prj_conf:
            structure["prj.conf"] = self.prj_conf
        if self.platformio_ini:
            structure["platformio.ini"] = self.platformio_ini
        if self.main_c:
            ext = "cpp" if self.platform and self.platform.language == "cpp" else "c"
            structure[f"src/main.{ext}"] = self.main_c

        for module in self.modules:
            structure[f"src/{module.filename}"] = module.code

        return structure

    def summary(self) -> str:
        """Return a human readable summary of the project."""
        return f"""
Firmware Project: {self.name} v{self.version}
Platform: {self.platform.name if self.platform else 'Unknown'}
MCU: {self.platform.mcu if self.platform else 'Unknown'}
Toolchain: {self.platform.toolchain if self.platform else 'Unknown'}
Modules: {', '.join(m.name for m in self.modules)}
Build: {'✅ Success' if self.build_success else '❌ Not built yet'}
Git: {self.git_repo_url or 'Not pushed'}
Nexus: {self.nexus_artifact_url or 'Not uploaded'}
Notion: {self.notion_doc_url or 'Not documented'}
        """.strip()


@dataclass
class RequirementsDoc:
    """Represents requirements read from Notion."""
    title: str
    device_name: str
    device_description: str
    target_users: str
    raw_content: str
    functional: list[str] = field(default_factory=list)
    hardware: list[str] = field(default_factory=list)
    electronics: list[str] = field(default_factory=list)
    software_firmware: list[str] = field(default_factory=list)
    performance: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)