from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, StreamingResponse
import json
import os
import tempfile
import gzip
import shutil

from app.models.schemas import SSHConnection
from app.core.dependencies import get_ssh_client
from app.utils.helpers import cleanup_temp_files

router = APIRouter()

@router.post("/containers", summary="Get remote running containers")
def list_remote_running_containers(conn: SSHConnection):
    client = get_ssh_client(conn)
    result = []
    try:
        # Provide -a to list all containers
        stdin, stdout, stderr = client.exec_command('docker ps -a --format "{{json .}}"')
        for line in stdout:
            if not line.strip(): continue
            data = json.loads(line)
            result.append({
                "id": data.get("ID"),
                "name": data.get("Names"),
                "status": data.get("Status"),
                "image": data.get("Image")
            })
        return {"containers": result}
    except Exception as e:
        err = stderr.read().decode('utf-8') if 'stderr' in locals() else str(e)
        raise HTTPException(status_code=500, detail=err)
    finally:
        client.close()

@router.post("/containers/{container_id}/inspect", summary="Get full remote container details")
def inspect_remote_container(container_id: str, conn: SSHConnection):
    """
    Returns the full equivalent of 'docker inspect <container>' on the remote host
    """
    client = get_ssh_client(conn)
    try:
        stdin, stdout, stderr = client.exec_command(f'docker inspect {container_id}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode('utf-8')
            raise HTTPException(status_code=404, detail=f"Container {container_id} not found: {err}")
        
        output = stdout.read().decode('utf-8')
        data = json.loads(output)
        if not data:
            raise HTTPException(status_code=404, detail=f"Container {container_id} not found.")
        return data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/containers/{container_id}/start", summary="Start remote container")
def start_remote_container(container_id: str, conn: SSHConnection):
    client = get_ssh_client(conn)
    try:
        stdin, stdout, stderr = client.exec_command(f'docker start {container_id}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise Exception(stderr.read().decode('utf-8'))
        return {"message": f"Container {container_id} started on remote."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/containers/{container_id}/stop", summary="Stop remote container")
def stop_remote_container(container_id: str, conn: SSHConnection):
    client = get_ssh_client(conn)
    try:
        stdin, stdout, stderr = client.exec_command(f'docker stop {container_id}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise Exception(stderr.read().decode('utf-8'))
        return {"message": f"Container {container_id} stopped on remote."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/containers/{container_id}/restart", summary="Restart remote container")
def restart_remote_container(container_id: str, conn: SSHConnection):
    client = get_ssh_client(conn)
    try:
        stdin, stdout, stderr = client.exec_command(f'docker restart {container_id}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise Exception(stderr.read().decode('utf-8'))
        return {"message": f"Container {container_id} restarted on remote."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/containers/{container_id}/logs/stdout", summary="Stream live container stdout/stderr logs")
def stream_remote_container_stdout_logs(container_id: str, conn: SSHConnection):
    """
    Streams the standard container logs (stdout/stderr).
    Equivalent to executing: docker logs -f --tail 25 <container>
    """
    client = get_ssh_client(conn)
    try:
        # Use docker logs instead of exec tail, with unbuffered pty
        stdin, stdout, stderr = client.exec_command(f'docker logs -f --tail 25 {container_id}', get_pty=True)
        
        def log_generator():
            try:
                while True:
                    line = stdout.readline()
                    if not line:
                        err = stderr.read().decode('utf-8')
                        if err:
                            yield f"Error reading stream: {err}".encode('utf-8')
                        break
                    yield line.encode('utf-8')
            finally:
                client.close()
                
        return StreamingResponse(log_generator(), media_type="text/plain")
        
    except Exception as e:
        client.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/logs/file", summary="Stream live file logs from remote container")
def stream_remote_container_file_logs(container_id: str, log_path: str, conn: SSHConnection):
    """
    Streams live logs from a specific file path inside the remote container.
    """
    client = get_ssh_client(conn)
    try:
        # Use python's context over the ssh stream to read output, with unbuffered pty
        stdin, stdout, stderr = client.exec_command(f'docker exec {container_id} tail -n 25 -f {log_path}', get_pty=True)
        
        def log_generator():
            try:
                # Read line by line until process dies or connection closes
                while True:
                    line = stdout.readline()
                    if not line:
                        err = stderr.read().decode('utf-8')
                        if err:
                            yield f"Error reading stream: {err}".encode('utf-8')
                        break
                    yield line.encode('utf-8')
            finally:
                # Close the SSH client when the streaming stops
                client.close()
                
        return StreamingResponse(log_generator(), media_type="text/plain")
        
    except Exception as e:
        client.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/containers/{container_id}", summary="Remove remote container",include_in_schema=False)
def remove_remote_container(container_id: str, conn: SSHConnection, force: bool = False):
    client = get_ssh_client(conn)
    force_flag = "-f" if force else ""
    try:
        stdin, stdout, stderr = client.exec_command(f'docker rm {force_flag} {container_id}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise Exception(stderr.read().decode('utf-8'))
        return {"message": f"Container {container_id} removed on remote."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/images", summary="Get remote Docker images")
def list_remote_docker_images(conn: SSHConnection):
    client = get_ssh_client(conn)
    result = []
    try:
        stdin, stdout, stderr = client.exec_command('docker images --format "{{json .}}"')
        for line in stdout:
            if not line.strip(): continue
            data = json.loads(line)
            result.append({
                "id": data.get("ID"),
                "image_name": [f"{data.get('Repository')}:{data.get('Tag')}"],
                "size_mb": data.get("Size")
            })
        return {"images": result}
    except Exception as e:
        err = stderr.read().decode('utf-8') if 'stderr' in locals() else str(e)
        raise HTTPException(status_code=500, detail=err)
    finally:
        client.close()

@router.delete("/images/{image_id:path}", summary="Remove remote image",include_in_schema=False)
def remove_remote_image(image_id: str, conn: SSHConnection, force: bool = False):
    client = get_ssh_client(conn)
    force_flag = "-f" if force else ""
    try:
        stdin, stdout, stderr = client.exec_command(f'docker rmi {force_flag} {image_id}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise Exception(stderr.read().decode('utf-8'))
        return {"message": f"Image {image_id} removed on remote."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/images/{image_name:path}/run", summary="Run a remote container from an image")
def run_remote_container_from_image(image_name: str, conn: SSHConnection, name: str = None):
    """
    Spawns and starts a new detached container from the specified remote image.
    Optionally accepts a container name via query parameter.
    """
    client = get_ssh_client(conn)
    name_flag = f"--name {name}" if name else ""
    try:
        # We run it detached (-d) in background
        stdin, stdout, stderr = client.exec_command(f'docker run -d {name_flag} {image_name}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            # If start fails, bubble up the error text
            raise Exception(stderr.read().decode('utf-8'))
            
        container_id = stdout.read().decode('utf-8').strip()
        # Return just the first 12 chars standard short ID
        if len(container_id) > 12:
            container_id = container_id[:12]
            
        return {
            "message": f"Container successfully started from {image_name} on remote.", 
            "id": container_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/volumes", summary="Get remote Docker volumes")
def list_remote_docker_volumes(conn: SSHConnection):
    client = get_ssh_client(conn)
    result = []
    try:
        stdin, stdout, stderr = client.exec_command('docker volume ls --format "{{json .}}"')
        for line in stdout:
            if not line.strip(): continue
            data = json.loads(line)
            result.append({
                "name": data.get("Name"),
                "driver": data.get("Driver"),
                "mountpoint": data.get("Mountpoint")
            })
        return {"volumes": result}
    except Exception as e:
        err = stderr.read().decode('utf-8') if 'stderr' in locals() else str(e)
        raise HTTPException(status_code=500, detail=err)
    finally:
        client.close()

@router.delete("/volumes/{volume_name:path}", summary="Remove remote volume",include_in_schema=False)
def remove_remote_volume(volume_name: str, conn: SSHConnection, force: bool = False):
    client = get_ssh_client(conn)
    force_flag = "-f" if force else ""
    try:
        stdin, stdout, stderr = client.exec_command(f'docker volume rm {force_flag} {volume_name}')
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise Exception(stderr.read().decode('utf-8'))
        return {"message": f"Volume {volume_name} removed on remote."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/images/download/{image_name:path}", summary="Download specific remote image as .tar.gz")
def download_remote_specific_image(image_name: str, conn: SSHConnection, background_tasks: BackgroundTasks):
    client = get_ssh_client(conn)
    
    fd, gz_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    
    try:
        stdin, stdout, stderr = client.exec_command(f"docker save {image_name}")
        
        with gzip.open(gz_path, 'wb') as f_out:
            while True:
                chunk = stdout.channel.recv(8192)
                if not chunk:
                    break
                f_out.write(chunk)
                
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_msg = stderr.read().decode('utf-8')
            raise Exception(f"Docker save failed: {error_msg}")
            
        background_tasks.add_task(cleanup_temp_files, gz_path)
        safe_name = image_name.replace(":", "_").replace("/", "_")
        return FileResponse(path=gz_path, filename=f"remote_{safe_name}.tar.gz", media_type="application/gzip")
    except Exception as e:
        cleanup_temp_files(gz_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/images/download-all", summary="Download all remote images as a single .tar.gz")
def download_remote_all_images(conn: SSHConnection, background_tasks: BackgroundTasks):
    client = get_ssh_client(conn)
    
    fd, gz_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    
    try:
        # Get all image tags
        stdin, stdout, stderr = client.exec_command("docker images --format '{{.Repository}}:{{.Tag}}'")
        images = [line.strip() for line in stdout if line.strip() and not "none:none" in line.strip()]
        
        if not images:
            raise Exception("No valid images found on remote machine")
            
        # Run docker save for all images
        image_str = " ".join(images)
        stdin, stdout, stderr = client.exec_command(f"docker save {image_str}")
        
        with gzip.open(gz_path, 'wb') as f_out:
            while True:
                chunk = stdout.channel.recv(8192)
                if not chunk:
                    break
                f_out.write(chunk)
                
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_msg = stderr.read().decode('utf-8')
            raise Exception(f"Docker save failed: {error_msg}")
            
        background_tasks.add_task(cleanup_temp_files, gz_path)
        return FileResponse(path=gz_path, filename="remote_all_images.tar.gz", media_type="application/gzip")
    except Exception as e:
        cleanup_temp_files(gz_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

@router.post("/images/download-individual", summary="Download all remote images as individual .tar.gz inside a .zip")
def download_remote_all_images_individual(conn: SSHConnection, background_tasks: BackgroundTasks):
    client = get_ssh_client(conn)
    
    temp_dir = tempfile.mkdtemp()
    fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    try:
        stdin, stdout, stderr = client.exec_command("docker images --format '{{.Repository}}:{{.Tag}}'")
        images = [line.strip() for line in stdout if line.strip() and not "none:none" in line.strip()]
        
        if not images:
            raise Exception("No valid images found on remote machine")
            
        for img in images:
            safe_name = img.replace(":", "_").replace("/", "_")
            gz_path = os.path.join(temp_dir, f"{safe_name}.tar.gz")
            
            try:
                stdin_s, stdout_s, stderr_s = client.exec_command(f"docker save {img}")
                with gzip.open(gz_path, 'wb') as f_out:
                    while True:
                        chunk = stdout_s.channel.recv(8192)
                        if not chunk:
                            break
                        f_out.write(chunk)
            except Exception:
                if os.path.exists(gz_path):
                    os.remove(gz_path)
                pass

        base_name = zip_path[:-4]
        shutil.make_archive(base_name, 'zip', temp_dir)
        
        def cleanup_all():
            shutil.rmtree(temp_dir, ignore_errors=True)
            cleanup_temp_files(zip_path)
            
        background_tasks.add_task(cleanup_all)
        return FileResponse(path=zip_path, filename="remote_individual_images.zip", media_type="application/zip")
    except Exception as e:
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if 'zip_path' in locals():
            cleanup_temp_files(zip_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()
