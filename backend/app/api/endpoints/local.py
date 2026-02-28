from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, StreamingResponse
import docker
import json
import os
import tempfile
import gzip
import shutil
import subprocess

from app.core.dependencies import get_docker_client
from app.utils.helpers import cleanup_temp_files

router = APIRouter()

@router.get("/containers", summary="Get running containers")
def list_running_containers():
    """
    Retrieve a list of all currently running Docker containers.
    """
    result = []
    try:
        proc = subprocess.run(['docker', 'ps', '-a', '--format', '{{json .}}'], capture_output=True, text=True, check=True)
        for line in proc.stdout.splitlines():
            if not line.strip(): continue
            data = json.loads(line)
            result.append({
                "id": data.get("ID"),
                "name": data.get("Names"),
                "status": data.get("Status"),
                "state": data.get("State", "N/A"),
                "health": "N/A", 
                "image": data.get("Image"),
                "created": data.get("CreatedAt"),
                "running_for": data.get("RunningFor"),
                "ports": data.get("Ports")
            })
        return {"containers": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}/inspect", summary="Get full container details")
def inspect_container(container_id: str):
    """
    Returns the full equivalent of 'docker inspect <container>'
    """
    try:
        proc = subprocess.run(['docker', 'inspect', container_id], capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
        if not data:
            raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
        return data[0]
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/start", summary="Start container")
def start_container(container_id: str):
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.start()
        return {"message": f"Container {container_id} started."}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/stop", summary="Stop container")
def stop_container(container_id: str):
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.stop()
        return {"message": f"Container {container_id} stopped."}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/restart", summary="Restart container")
def restart_container(container_id: str):
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.restart()
        return {"message": f"Container {container_id} restarted."}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}/logs/stdout", summary="Stream live container stdout/stderr logs")
def stream_container_stdout_logs(container_id: str):
    """
    Streams the standard container logs (stdout/stderr).
    Equivalent to executing: docker logs -f --tail 25 <container>
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        
        # Stream the output directly using standard container logs
        def log_generator():
            try:
                for chunk in container.logs(stream=True, follow=True, tail=25, stdout=True, stderr=True):
                    if chunk:
                        yield chunk
            except Exception as e:
                yield f"Error reading stream: {str(e)}".encode('utf-8')
                
        return StreamingResponse(log_generator(), media_type="text/plain")
        
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}/logs/file", summary="Stream live file logs from container")
def stream_container_file_logs(container_id: str, log_path: str):
    """
    Streams live logs from a specific file path inside the container.
    Equivalent to executing: docker exec <container> tail -n 25 -f <log_path>
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        
        # Stream the output of the tail command from inside the container
        exit_code, output_gen = container.exec_run(["tail", "-n", "25", "-f", log_path], stream=True)
        
        def log_generator():
            try:
                for chunk in output_gen:
                    if chunk:
                        yield chunk
            except Exception as e:
                yield f"Error reading stream: {str(e)}".encode('utf-8')
                
        return StreamingResponse(log_generator(), media_type="text/plain")
        
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/containers/{container_id}", summary="Remove container")
def remove_container(container_id: str, force: bool = False):
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.remove(force=force)
        return {"message": f"Container {container_id} removed."}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/images", summary="Get Docker images")
def list_docker_images():
    """
    Retrieve a list of all Docker images available on the machine.
    """
    result = []
    try:
        proc = subprocess.run(['docker', 'images', '--format', '{{json .}}'], capture_output=True, text=True, check=True)
        for line in proc.stdout.splitlines():
            if not line.strip(): continue
            data = json.loads(line)
            result.append({
                "id": data.get("ID"),
                "image_name": [f"{data.get('Repository')}:{data.get('Tag')}"],
                "size_mb": data.get("Size"),
                "created": data.get("CreatedAt")
            })
        return {"images": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/images/{image_id:path}", summary="Remove image")
def remove_image(image_id: str, force: bool = False):
    client = get_docker_client()
    try:
        client.images.remove(image=image_id, force=force)
        return {"message": f"Image {image_id} removed."}
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/images/{image_name:path}/run", summary="Run a container from an image")
def run_container_from_image(image_name: str, name: str = None):
    """
    Spawns and starts a new detached container from the specified image.
    Optionally accepts a container name via query parameter.
    """
    client = get_docker_client()
    try:
        # We run it detached (-d), so it starts in background
        container = client.containers.run(image_name, detach=True, name=name)
        return {
            "message": f"Container successfully started from {image_name}.", 
            "id": container.short_id
        }
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=404, detail=f"Image {image_name} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/volumes", summary="Get Docker volumes")
def list_docker_volumes():
    """
    Retrieve a list of all Docker volumes.
    """
    result = []
    try:
        proc = subprocess.run(['docker', 'volume', 'ls', '--format', '{{json .}}'], capture_output=True, text=True, check=True)
        for line in proc.stdout.splitlines():
            if not line.strip(): continue
            data = json.loads(line)
            result.append({
                "name": data.get("Name"),
                "driver": data.get("Driver"),
                "mountpoint": data.get("Mountpoint", ""),
                "labels": data.get("Labels", "")
            })
        return {"volumes": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/volumes/{volume_name:path}", summary="Remove volume")
def remove_volume(volume_name: str, force: bool = False):
    client = get_docker_client()
    try:
        volume = client.volumes.get(volume_name)
        volume.remove(force=force)
        return {"message": f"Volume {volume_name} removed."}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Volume {volume_name} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/images/download/{image_name:path}", summary="Download a specific image as .tar.gz")
def download_specific_image(image_name: str, background_tasks: BackgroundTasks):
    """
    Export a specific Docker image and download it as a GZIP compressed tarball (.tar.gz).
    """
    client = get_docker_client()
    try:
        image = client.images.get(image_name)
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=404, detail=f"Image {image_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Create temporary file to store the compressed tarball
    fd, gz_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)

    try:
        # Create a compressed GZIP file from the image stream
        with gzip.open(gz_path, 'wb') as f_out:
            for chunk in image.save(named=True):
                f_out.write(chunk)
                
        # Register cleanup to run after response is sent
        background_tasks.add_task(cleanup_temp_files, gz_path)
        
        safe_name = image_name.replace(":", "_").replace("/", "_")
        return FileResponse(
            path=gz_path, 
            filename=f"{safe_name}.tar.gz", 
            media_type="application/gzip"
        )
    except Exception as e:
        cleanup_temp_files(gz_path)
        raise HTTPException(status_code=500, detail=f"Failed to save image: {str(e)}")

@router.get("/images/download-all", summary="Download all images as a single .tar.gz")
def download_all_images(background_tasks: BackgroundTasks):
    """
    Export all available Docker images into a single GZIP compressed tarball (.tar.gz).
    """
    client = get_docker_client()
    try:
        images = client.images.list()
        if not images:
            raise HTTPException(status_code=404, detail="No images found on this machine")
            
        # Collect all image tags or IDs
        image_identifiers = []
        for img in images:
            if img.tags:
                image_identifiers.extend(img.tags)
            else:
                # Fallback to short ID if untagged
                image_identifiers.append(img.short_id)
                
        fd_tar, tar_path = tempfile.mkstemp(suffix=".tar")
        fd_gz, gz_path = tempfile.mkstemp(suffix=".tar.gz")
        os.close(fd_tar)
        os.close(fd_gz)
        
        # We use docker CLI directly here because docker-py doesn't easily support saving multiple images to a single archive
        cmd = ["docker", "save", "-o", tar_path] + image_identifiers
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Compress the tar file
        with open(tar_path, 'rb') as f_in:
            with gzip.open(gz_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
                
        # Register cleanup for both temp files
        background_tasks.add_task(cleanup_temp_files, tar_path, gz_path)
        
        return FileResponse(
            path=gz_path, 
            filename="all_docker_images.tar.gz", 
            media_type="application/gzip"
        )
        
    except subprocess.CalledProcessError as e:
        cleanup_temp_files(tar_path, gz_path)
        raise HTTPException(status_code=500, detail=f"Failed to save all images (Docker Error): {e.stderr}")
    except Exception as e:
        cleanup_temp_files(vars().get('tar_path'), vars().get('gz_path'))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/images/download-individual", summary="Download all images as individual .tar.gz inside a .zip")
def download_all_images_individual(background_tasks: BackgroundTasks):
    """
    Export all available Docker images as individual .tar.gz files, and bundle them into a single .zip file.
    """
    client = get_docker_client()
    try:
        images = client.images.list()
        if not images:
            raise HTTPException(status_code=404, detail="No images found on this machine")
            
        # Create a temporary directory to store individual tar.gz files
        temp_dir = tempfile.mkdtemp()
        
        for img in images:
            if img.tags:
                image_name = img.tags[0]
                safe_name = image_name.replace(":", "_").replace("/", "_")
            else:
                image_name = img.short_id
                safe_name = image_name
            
            gz_path = os.path.join(temp_dir, f"{safe_name}.tar.gz")
            
            try:
                # Get the image object to save
                image_obj = client.images.get(image_name)
                with gzip.open(gz_path, 'wb') as f_out:
                    for chunk in image_obj.save(named=True):
                        f_out.write(chunk)
            except Exception:
                # If an individual image fails to save, clean the partial file and continue
                if os.path.exists(gz_path):
                    os.remove(gz_path)
                pass
                
        # Zip the directory
        fd, zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        
        # Remove the .zip extension because make_archive appends it automatically
        base_name = zip_path[:-4]
        shutil.make_archive(base_name, 'zip', temp_dir)
        
        # We need to clean up both the temp_dir and the zip_path
        def cleanup_all():
            shutil.rmtree(temp_dir, ignore_errors=True)
            cleanup_temp_files(zip_path)
            
        background_tasks.add_task(cleanup_all)
        
        return FileResponse(
            path=zip_path, 
            filename="individual_docker_images.zip", 
            media_type="application/zip"
        )
        
    except Exception as e:
        # In case of early failure
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if 'zip_path' in locals():
            cleanup_temp_files(zip_path)
        raise HTTPException(status_code=500, detail=str(e))
