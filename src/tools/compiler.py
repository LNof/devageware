
import os
import subprocess
import shutil
from dotenv import load_dotenv
from src.models import FirmwareProject

load_dotenv()

NCS_TOOLCHAIN_PATH = os.getenv("NCS_TOOLCHAIN_PATH", "/home/LoayN/ncs/toolchains/2ac5840438")
NCS_SDK_PATH = os.getenv("NCS_SDK_PATH", "/home/LoayN/ncs/v3.2.4")
NCS_WORKSPACE = os.getenv("NCS_WORKSPACE", "/home/LoayN/ncs-workspaces")

def _run_command(cmd: list[str], cwd: str, env: dict = None) -> tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    print(f"  ▶ Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env or os.environ.copy(),
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr

def _get_ncs_environment() -> dict:
    """Get the environment variables needed for NCS builds."""
    env = os.environ.copy()
    
    # add NCS toolchain to PATH
    toolchain_bin = os.path.join(NCS_TOOLCHAIN_PATH, "usr", "local", "bin")
    toolchain_sbin = os.path.join(NCS_TOOLCHAIN_PATH, "usr", "bin")
    env["PATH"] = f"{toolchain_bin}:{toolchain_sbin}:{env.get('PATH', '')}"
    
    # set Zephyr base
    env["ZEPHYR_BASE"] = os.path.join(NCS_SDK_PATH, "zephyr")
    
    # set NCS toolchain
    env["ZEPHYR_TOOLCHAIN_VARIANT"] = "gnuarmemb"
    env["GNUARMEMB_TOOLCHAIN_PATH"] = NCS_TOOLCHAIN_PATH
    
    return env

def build_ncs_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    """Build an NCS/Zephyr project using west."""
    print(f"\n🔨 Building NCS project: {project.name}")
    print(f"   Board: {project.platform.board}")
    print(f"   Project dir: {project_dir}")

    build_dir = os.path.join(project_dir, "build")
    env = _get_ncs_environment()
    west_bin = os.path.join(NCS_TOOLCHAIN_PATH, "usr", "local", "bin", "west")

    # clean previous build
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    # run west build
    cmd = [
        west_bin, "build",
        "-b", project.platform.board or "nrf54l15dk",
        "--build-dir", build_dir,
        project_dir
    ]

    returncode, stdout, stderr = _run_command(cmd, cwd=project_dir, env=env)

    build_log = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    if returncode == 0:
        print("  ✅ Build successful!")
        # find the .bin and .hex files
        bin_path = _find_build_artifact(build_dir, ".bin")
        hex_path = _find_build_artifact(build_dir, ".hex")
        project.bin_path = bin_path
        project.hex_path = hex_path
        project.build_success = True
        project.build_log = build_log
        return True, build_log
    else:
        print(f"  ❌ Build failed!")
        print(f"  {stderr[:500]}")
        project.build_success = False
        project.build_log = build_log
        return False, build_log

def build_platformio_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    """Build a PlatformIO/Arduino project."""
    # quote the project dir to handle spaces
    import shlex
    project_dir = os.path.abspath(project_dir)

    print(f"\n🔨 Building PlatformIO project: {project.name}")
    print(f"   Board: {project.platform.board}")
    print(f"   Project dir: {project_dir}")

    pio_bin = shutil.which("pio") or shutil.which("platformio")
    if not pio_bin:
        return False, "PlatformIO not found — run: pip install platformio"

    cmd = [pio_bin, "run", "--project-dir", project_dir]
    returncode, stdout, stderr = _run_command(cmd, cwd=project_dir)

    build_log = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    if returncode == 0:
        print("  ✅ Build successful!")
        # find .bin in .pio/build directory
        bin_path = _find_build_artifact(
            os.path.join(project_dir, ".pio", "build"),
            ".bin"
        )
        hex_path = _find_build_artifact(
            os.path.join(project_dir, ".pio", "build"),
            ".hex"
        )
        project.bin_path = bin_path
        project.hex_path = hex_path
        project.build_success = True
        project.build_log = build_log
        return True, build_log
    else:
        print(f"  ❌ Build failed!")
        print(f"  {stderr[:500]}")
        project.build_success = False
        project.build_log = build_log
        return False, build_log

def build_mcuxpresso_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    """Build an NXP MCUXpresso project using CMake and Ninja."""
    print(f"\n🔨 Building MCUXpresso project: {project.name}")
    print(f"   MCU: {project.platform.mcu}")
    print(f"   Project dir: {project_dir}")

    build_dir = os.path.join(project_dir, "build")
    os.makedirs(build_dir, exist_ok=True)

    # cmake configure
    cmake_cmd = [
        "cmake", "..",
        "-G", "Ninja",
        "-DCMAKE_TOOLCHAIN_FILE=arm-none-eabi.cmake"
    ]
    returncode, stdout, stderr = _run_command(cmake_cmd, cwd=build_dir)

    if returncode != 0:
        build_log = f"CMake configure failed:\n{stderr}"
        project.build_success = False
        project.build_log = build_log
        return False, build_log

    # ninja build
    ninja_cmd = ["ninja"]
    returncode, stdout, stderr = _run_command(ninja_cmd, cwd=build_dir)
    build_log = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    if returncode == 0:
        print("  ✅ Build successful!")
        bin_path = _find_build_artifact(build_dir, ".bin")
        hex_path = _find_build_artifact(build_dir, ".hex")
        project.bin_path = bin_path
        project.hex_path = hex_path
        project.build_success = True
        project.build_log = build_log
        return True, build_log
    else:
        print(f"  ❌ Build failed!")
        project.build_success = False
        project.build_log = build_log
        return False, build_log

def _find_build_artifact(build_dir: str, extension: str) -> str | None:
    """Recursively find a build artifact by extension."""
    for root, dirs, files in os.walk(build_dir):
        for file in files:
            if file.endswith(extension):
                return os.path.join(root, file)
    return None

def compile_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    """Compile the project using the appropriate toolchain."""
    toolchain = project.platform.toolchain.lower() if project.platform else ""

    if toolchain == "ncs":
        return build_ncs_project(project, project_dir)
    elif toolchain == "platformio":
        return build_platformio_project(project, project_dir)
    elif toolchain == "mcuxpresso":
        return build_mcuxpresso_project(project, project_dir)
    else:
        return False, f"Unknown toolchain: {toolchain}"