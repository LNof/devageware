from importlib.resources import files
import json
import os
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv, version
from src.models import FirmwareProject, FirmwareModule, Platform

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY")
)

def extract_json_from_response(text: str) -> str | None:
    """Extract JSON block from LLM response text."""
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        return text[start:end].strip()

    if "{" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        return text[start:end].strip()

    return None

def parse_firmware_json(json_str: str) -> FirmwareProject:
    """Parse the JSON output from the LLM into a FirmwareProject."""
    data = json.loads(json_str)

    # parse platform
    platform_data = data.get("platform", {})

    # normalise toolchain first
    toolchain = platform_data.get("toolchain", "unknown").lower()
    if toolchain in ["arduino", "arduino/platformio"]:
        toolchain = "platformio"
    
    if toolchain=="platformio":
        language = "cpp"

    platform = Platform(
        name=platform_data.get("name", "Unknown"),
        vendor=platform_data.get("vendor", "Unknown"),
        mcu=platform_data.get("mcu", "Unknown"),
        toolchain=toolchain,
        language=language,
        board=platform_data.get("board", None)
    )

    # set toolchain paths based on vendor
    if platform.vendor.lower() == "nordic":
        platform.toolchain_path = os.getenv("NCS_TOOLCHAIN_PATH")
        platform.sdk_path = os.getenv("NCS_SDK_PATH", "/home/LoayN/ncs/v3.2.4")

    # parse project info
    project_data = data.get("project", {})

    version = project_data.get("version", "0.1.0")
    version = version.lstrip("v")  # remove leading 'v' if present

    project = FirmwareProject(
        name=project_data.get("name", "firmware"),
        version=version,
        description=project_data.get("description", ""),
        platform=platform
    )

    # parse files
    files = data.get("files", {})
    print(f"  🔍 File keys: {list(files.keys())}")
    for k, v in files.items():
        print(f"  🔍 {k}: {len(v) if v else 0} chars")

    project.cmakelists = files.get("CMakeLists.txt", "")
    project.prj_conf = files.get("prj.conf", "")
    project.platformio_ini = files.get("platformio.ini", "")

    # find main source file
    ext = "cpp" if platform.language == "cpp" else "c"
    project.main_c = (
        files.get(f"src/main.{ext}") or
        files.get("src/main.cpp") or
        files.get("src/main.c") or
        files.get("main.cpp") or
        files.get("main.c") or
        ""
    )

    # parse all remaining files as modules
    skip_keys = {
        "CMakeLists.txt", "prj.conf", "platformio.ini",
        f"src/main.{ext}", "src/main.cpp", "src/main.c",
        "main.cpp", "main.c"
    }

    for filename, code in files.items():
        if filename not in skip_keys and code:
            base_filename = filename.split("/")[-1]
            project.modules.append(FirmwareModule(
                name=base_filename.split(".")[0],
                filename=base_filename,
                description=f"Module: {base_filename}",
                code=code
            ))

    return project

def save_project_to_disk(project: FirmwareProject, output_dir: str = "output") -> str:
    """Save all project files to disk."""
    # replace spaces with underscores to avoid path issues
    safe_name = project.name.replace(" ", "_")
    project_dir = os.path.join(output_dir, safe_name)

    # clean previous build
    if os.path.exists(project_dir):
        import shutil
        shutil.rmtree(project_dir)

    os.makedirs(project_dir, exist_ok=True)

    # write all files
    structure = project.get_project_structure()
    for filepath, content in structure.items():
        full_path = os.path.join(project_dir, filepath)
        # create subdirectories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        print(f"  📄 Written: {filepath}")

    return project_dir

def generate_documentation(project: FirmwareProject) -> str:
    """Generate markdown documentation for the firmware project."""
    lines = []

    # frontmatter
    lines.append("---")
    lines.append(f"title: {project.name} Firmware Documentation")
    lines.append(f"version: {project.version}")
    lines.append(f"created: {project.created_at}")
    lines.append(f"platform: {project.platform.name if project.platform else 'Unknown'}")
    lines.append(f"tags: [firmware, {project.platform.vendor.lower() if project.platform else 'unknown'}]")
    lines.append("---")
    lines.append("")

    # header
    lines.append(f"# {project.name} — Firmware Documentation")
    lines.append(f"> Version: {project.version} | Generated: {project.created_at}")
    lines.append("")

    # platform info
    lines.append("## 🖥️ Platform")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|---|---|")
    if project.platform:
        lines.append(f"| **MCU** | {project.platform.mcu} |")
        lines.append(f"| **Vendor** | {project.platform.vendor} |")
        lines.append(f"| **Board** | {project.platform.board or 'Custom'} |")
        lines.append(f"| **Toolchain** | {project.platform.toolchain} |")
        lines.append(f"| **Language** | {project.platform.language.upper()} |")
    lines.append("")

    # project overview
    lines.append("## 📋 Overview")
    lines.append(f"{project.description}")
    lines.append("")

    # build instructions
    lines.append("## 🔨 Build Instructions")
    lines.append("")
    if project.platform and project.platform.toolchain == "ncs":
        lines.append("### nRF Connect SDK (Zephyr)")
        lines.append("```bash")
        lines.append("# initialise workspace")
        lines.append("west init -l .")
        lines.append("west update")
        lines.append("")
        lines.append("# build")
        lines.append(f"west build -b {project.platform.board or 'nrf54l15dk'} .")
        lines.append("")
        lines.append("# flash")
        lines.append(f"west flash")
        lines.append("```")
    elif project.platform and project.platform.toolchain == "platformio":
        lines.append("### PlatformIO")
        lines.append("```bash")
        lines.append("# build")
        lines.append("pio run")
        lines.append("")
        lines.append("# flash")
        lines.append("pio run --target upload")
        lines.append("")
        lines.append("# serial monitor")
        lines.append("pio device monitor")
        lines.append("```")
    elif project.platform and project.platform.toolchain == "mcuxpresso":
        lines.append("### MCUXpresso SDK")
        lines.append("```bash")
        lines.append("mkdir build && cd build")
        lines.append("cmake .. -G Ninja")
        lines.append("ninja")
        lines.append("```")
    lines.append("")

    # modules
    if project.modules:
        lines.append("## 📦 Modules")
        lines.append("")
        for module in project.modules:
            lines.append(f"### `{module.filename}`")
            lines.append(f"{module.description}")
            lines.append("")

    # source files
    lines.append("## 📁 Project Structure")
    lines.append("```")
    lines.append(f"{project.name}/")
    structure = project.get_project_structure()
    for filepath in structure.keys():
        lines.append(f"├── {filepath}")
    lines.append("```")
    lines.append("")

    # artifact locations
    lines.append("## 🚀 Artifacts")
    lines.append("")
    lines.append(f"| Artifact | Location |")
    lines.append(f"|---|---|")
    lines.append(f"| Source Code | {project.git_repo_url or 'Not pushed yet'} |")
    lines.append(f"| Binary (.bin) | {project.nexus_artifact_url or 'Not uploaded yet'} |")
    lines.append("")

    return "\n".join(lines)