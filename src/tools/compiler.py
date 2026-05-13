import os
import shutil
import subprocess
from dotenv import load_dotenv
from src.models import FirmwareProject, Platform

load_dotenv()

NEXUS_DOCKER_REGISTRY = os.getenv("NEXUS_DOCKER_REGISTRY", "10.0.0.221:8082")

# vendor/toolchain → image name (tag included)
_IMAGE_MAP = {
    "platformio": "arduino-toolchain:latest",
    "arduino": "arduino-toolchain:latest",
    "ncs": "ncs-toolchain:v3.2.4",
    "mcuxpresso": "zephyr-toolchain:v4.3.0",
    "zephyr": "zephyr-toolchain:v4.3.0",
}


def image_for(platform: Platform) -> str:
    """Return the registry-qualified container image for this platform."""
    key = (platform.toolchain or "").lower()
    image = _IMAGE_MAP.get(key)
    if not image:
        raise ValueError(f"No toolchain container known for toolchain '{platform.toolchain}'")
    return f"{NEXUS_DOCKER_REGISTRY}/{image}"


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    print(f"  ▶ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def _require_docker() -> None:
    if not shutil.which("docker"):
        raise RuntimeError("docker not found on PATH — install docker before running the build")


def _docker_pull(image: str) -> tuple[bool, str]:
    print(f"\n📦 Pulling toolchain container: {image}")
    rc, out, err = _run(["docker", "pull", image])
    if rc == 0:
        return True, out
    return False, err or out


def _docker_build(image: str, project_dir: str, build_cmd: str) -> tuple[int, str, str]:
    """Run build_cmd inside the container with project_dir mounted at /workspace.

    Runs the command as root (container default) then chowns the workspace back
    to the host user so the host can clean it up between runs.
    """
    uid = os.getuid()
    gid = os.getgid()
    wrapped = f"{build_cmd}; rc=$?; chown -R {uid}:{gid} /workspace; exit $rc"
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{project_dir}:/workspace",
        "-w", "/workspace",
        image,
        "bash", "-lc", wrapped,
    ]
    return _run(cmd)


def build_platformio_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    project_dir = os.path.abspath(project_dir)
    image = image_for(project.platform)
    print(f"\n🔨 Building PlatformIO project: {project.name}")
    print(f"   Board: {project.platform.board}")
    print(f"   Project dir: {project_dir}")

    _require_docker()
    ok, pull_log = _docker_pull(image)
    if not ok:
        return False, f"docker pull failed:\n{pull_log}"

    rc, out, err = _docker_build(image, project_dir, "pio run --project-dir /workspace")
    build_log = f"STDOUT:\n{out}\n\nSTDERR:\n{err}"

    if rc == 0:
        print("  ✅ Build successful!")
        project.bin_path = _find_build_artifact(os.path.join(project_dir, ".pio", "build"), ".bin")
        project.hex_path = _find_build_artifact(os.path.join(project_dir, ".pio", "build"), ".hex")
        project.build_success = True
        project.build_log = build_log
        return True, build_log

    print(f"  ❌ Build failed!")
    print(f"  {err[:500]}")
    project.build_success = False
    project.build_log = build_log
    return False, build_log


def build_ncs_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    project_dir = os.path.abspath(project_dir)
    image = image_for(project.platform)
    board = project.platform.board or "nrf54l15dk"
    print(f"\n🔨 Building NCS project: {project.name}")
    print(f"   Board: {board}")
    print(f"   Project dir: {project_dir}")

    _require_docker()
    ok, pull_log = _docker_pull(image)
    if not ok:
        return False, f"docker pull failed:\n{pull_log}"

    build_cmd = f"west build -b {board} --build-dir /workspace/build /workspace"
    rc, out, err = _docker_build(image, project_dir, build_cmd)
    build_log = f"STDOUT:\n{out}\n\nSTDERR:\n{err}"

    if rc == 0:
        print("  ✅ Build successful!")
        build_dir = os.path.join(project_dir, "build")
        project.bin_path = _find_build_artifact(build_dir, ".bin")
        project.hex_path = _find_build_artifact(build_dir, ".hex")
        project.build_success = True
        project.build_log = build_log
        return True, build_log

    print(f"  ❌ Build failed!")
    print(f"  {err[:500]}")
    project.build_success = False
    project.build_log = build_log
    return False, build_log


def build_mcuxpresso_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    """Build an NXP/Zephyr project using the zephyr-toolchain container."""
    project_dir = os.path.abspath(project_dir)
    image = image_for(project.platform)
    board = project.platform.board or "mimxrt1062_evk"
    print(f"\n🔨 Building Zephyr project: {project.name}")
    print(f"   Board: {board}")
    print(f"   Project dir: {project_dir}")

    _require_docker()
    ok, pull_log = _docker_pull(image)
    if not ok:
        return False, f"docker pull failed:\n{pull_log}"

    build_cmd = f"west build -b {board} --build-dir /workspace/build /workspace"
    rc, out, err = _docker_build(image, project_dir, build_cmd)
    build_log = f"STDOUT:\n{out}\n\nSTDERR:\n{err}"

    if rc == 0:
        print("  ✅ Build successful!")
        build_dir = os.path.join(project_dir, "build")
        project.bin_path = _find_build_artifact(build_dir, ".bin")
        project.hex_path = _find_build_artifact(build_dir, ".hex")
        project.build_success = True
        project.build_log = build_log
        return True, build_log

    print(f"  ❌ Build failed!")
    print(f"  {err[:500]}")
    project.build_success = False
    project.build_log = build_log
    return False, build_log


def _find_build_artifact(build_dir: str, extension: str) -> str | None:
    if not os.path.isdir(build_dir):
        return None
    for root, _dirs, files in os.walk(build_dir):
        for file in files:
            if file.endswith(extension):
                return os.path.join(root, file)
    return None


def compile_project(project: FirmwareProject, project_dir: str) -> tuple[bool, str]:
    toolchain = (project.platform.toolchain or "").lower() if project.platform else ""

    if toolchain in ("ncs",):
        return build_ncs_project(project, project_dir)
    if toolchain in ("platformio", "arduino"):
        return build_platformio_project(project, project_dir)
    if toolchain in ("mcuxpresso", "zephyr"):
        return build_mcuxpresso_project(project, project_dir)
    return False, f"Unknown toolchain: {toolchain}"
