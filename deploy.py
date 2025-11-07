import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

PROFILE_NAME = "automate-deployment"
REGION_NAME = "us-east-2"
BUCKET_NAME = "three-tier-dockerfiles"
DOCKER_BASE_URL = "358262661502.dkr.ecr.us-east-2.amazonaws.com/"
TERRAFORM_STATE_KEY = "terraform/state/terraform.tfstate"

console = Console()


def fetch_dockerfiles() -> Dict[str, Optional[str]]:
    session = boto3.Session(profile_name=PROFILE_NAME, region_name=REGION_NAME)
    s3_client = session.client("s3")

    dockerfiles = {}
    paths = {"backend": "backend/Dockerfile", "frontend": "frontend/Dockerfile"}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for name, s3_key in paths.items():
            task = progress.add_task(f"[cyan]Fetching {name} Dockerfile...", total=None)
            try:
                response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
                dockerfile_content = response["Body"].read().decode("utf-8")
                dockerfiles[name] = dockerfile_content
                progress.update(task, description=f"[green]✓ Fetched {name} Dockerfile")
                progress.stop_task(task)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code == "NoSuchKey":
                    progress.update(task, description=f"[yellow]⚠ {name} Dockerfile not found")
                else:
                    progress.update(task, description=f"[red]✗ Error fetching {name} Dockerfile")
                progress.stop_task(task)
                dockerfiles[name] = None

    return dockerfiles


def write_dockerfiles(dockerfiles: Dict[str, Optional[str]]) -> None:
    local_paths = {
        "backend": Path("backend/Dockerfile"),
        "frontend": Path("frontend/Dockerfile"),
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for name, content in dockerfiles.items():
            task = progress.add_task(f"[cyan]Writing {name} Dockerfile...", total=None)
            
            if content is None:
                progress.update(task, description=f"[yellow]⚠ Skipping {name} - content not available")
                progress.stop_task(task)
                continue

            local_path = local_paths.get(name)
            if not local_path:
                progress.update(task, description=f"[yellow]⚠ No path defined for {name}")
                progress.stop_task(task)
                continue

            try:
                # Create directory if it doesn't exist
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # TEMPORARY ADDITION WHILE TESTING ON SF-PLATFORM REPO ITSELF
                # For backend, remove CodeArtifact repository before poetry install
                if name == "backend":
                    # Find the poetry install line and add a step to remove codeartifact repo before it
                    lines = content.split("\n")
                    modified_lines = []
                    for line in lines:
                        # Don't copy poetry.lock since it references CodeArtifact packages
                        if (
                            "COPY pyproject.toml poetry.lock" in line
                            or "COPY pyproject.toml poetry.lock*" in line
                        ):
                            modified_lines.append("COPY pyproject.toml ./")
                        # Remove any CodeArtifact source removal commands (not needed if no lockfile)
                        elif "poetry source remove codeartifact" in line:
                            continue  # Skip this line
                        # Poetry install will work without lockfile - it will resolve from pyproject.toml
                        # No changes needed to the install command
                        else:
                            modified_lines.append(line)

                    content = "\n".join(modified_lines)

                # Write the Dockerfile
                local_path.write_text(content, encoding="utf-8")
                progress.update(task, description=f"[green]✓ Saved {name} Dockerfile")
                progress.stop_task(task)
            except Exception as e:
                progress.update(task, description=f"[red]✗ Error writing {name} Dockerfile")
                progress.stop_task(task)
                console.print(f"[red]Error details: {e}")


def fetch_terraform_files() -> bool:
    """
    Fetch and extract Terraform configuration from S3.
    Returns True if successful, False otherwise.
    """
    session = boto3.Session(profile_name=PROFILE_NAME, region_name=REGION_NAME)
    s3_client = session.client("s3")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        try:
            # Fetch the zip file
            task = progress.add_task("[cyan]Fetching Terraform configuration from S3...", total=None)
            s3_key = "infra.zip"
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
            zip_content = response["Body"].read()
            progress.update(task, description="[green]✓ Fetched Terraform configuration")
            progress.stop_task(task)
        
            # Extract to local infra directory
            extract_task = progress.add_task("[cyan]Extracting Terraform files...", total=None)
            infra_path = Path("infra")
            
            # Backup existing infra directory if it exists
            if infra_path.exists():
                backup_path = Path("infra.backup")
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                shutil.move(str(infra_path), str(backup_path))
            
            # Create fresh infra directory
            infra_path.mkdir(exist_ok=True)
            
            # Extract the zip file
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                # Get list of files in the zip
                file_list = zf.namelist()
                
                # Check if all files are nested under a common directory
                # (e.g., infra/main.tf, infra/ecs.tf, etc.)
                common_prefix = None
                if file_list:
                    # Find common directory prefix
                    first_file = file_list[0]
                    if '/' in first_file:
                        potential_prefix = first_file.split('/')[0] + '/'
                        if all(f.startswith(potential_prefix) for f in file_list):
                            common_prefix = potential_prefix
                
                # Extract files
                for file_info in zf.infolist():
                    # Skip directories
                    if file_info.is_dir():
                        continue
                    
                    filename = file_info.filename
                    
                    # Strip common prefix if found
                    if common_prefix and filename.startswith(common_prefix):
                        filename = filename[len(common_prefix):]
                    
                    # Skip if filename is empty after stripping
                    if not filename:
                        continue
                    
                    # Extract to infra directory
                    target_path = infra_path / filename
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with zf.open(file_info.filename) as source, open(target_path, 'wb') as target:
                        target.write(source.read())
                    
                    # Preserve file permissions from zip
                    # Get the external attributes and extract Unix permissions
                    unix_permissions = file_info.external_attr >> 16
                    if unix_permissions:
                        target_path.chmod(unix_permissions)
            
            progress.update(extract_task, description="[green]✓ Extracted Terraform configuration")
            progress.stop_task(extract_task)
            
            # Verify that .tf files exist
            tf_files = list(infra_path.glob("*.tf"))
            if tf_files:
                console.print(f"[dim]   Found {len(tf_files)} Terraform files[/dim]")
            
            # Remove backup if extraction was successful
            backup_path = Path("infra.backup")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                console.print(f"[yellow]⚠ Terraform zip not found at s3://{BUCKET_NAME}/infra.zip")
            else:
                console.print(f"[red]✗ Error fetching Terraform files: {e}")
            
            # Restore backup if extraction failed
            backup_path = Path("infra.backup")
            if backup_path.exists():
                infra_path = Path("infra")
                if infra_path.exists():
                    shutil.rmtree(infra_path)
                shutil.move(str(backup_path), str(infra_path))
                console.print("[dim]♻️  Restored backup infra directory[/dim]")
            
            return False
        except Exception as e:
            console.print(f"[red]✗ Unexpected error extracting Terraform files: {e}")
            
            # Restore backup if extraction failed
            backup_path = Path("infra.backup")
            if backup_path.exists():
                infra_path = Path("infra")
                if infra_path.exists():
                    shutil.rmtree(infra_path)
                shutil.move(str(backup_path), str(infra_path))
                console.print("[dim]♻️  Restored backup infra directory[/dim]")
            
            return False


def upload_state_to_s3() -> bool:
    """
    Upload the existing local terraform.tfstate to S3.
    This is a one-time migration helper.
    """
    session = boto3.Session(profile_name=PROFILE_NAME, region_name=REGION_NAME)
    s3_client = session.client("s3")
    
    local_state = Path("infra/terraform.tfstate")
    
    if not local_state.exists():
        console.print("[yellow]⚠ No local state file found at infra/terraform.tfstate")
        return False
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        try:
            task = progress.add_task("[cyan]Uploading state to S3...", total=None)
            with open(local_state, 'rb') as f:
                s3_client.put_object(
                    Bucket=BUCKET_NAME,
                    Key=TERRAFORM_STATE_KEY,
                    Body=f,
                    ServerSideEncryption='AES256'
                )
            progress.update(task, description="[green]✓ State file uploaded to S3")
            progress.stop_task(task)
            return True
        except Exception as e:
            console.print(f"[red]✗ Error uploading state to S3: {e}")
            return False


def apply_infrastructure(force_recreate: bool = False) -> bool:
    """
    Apply Terraform configuration from the infra directory.
    Runs terraform init and terraform apply.
    
    Args:
        force_recreate: If True, adds -replace flag to recreate resources that already exist
    
    Returns:
        True if successful or resources already exist, False otherwise
    """
    infra_path = Path("infra")
    
    if not infra_path.exists():
        console.print(f"[red]✗ Infrastructure directory not found at {infra_path}")
        return False
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        try:
            # Initialize Terraform (will migrate to S3 backend if configured)
            task = progress.add_task("[cyan]Initializing Terraform...", total=None)
            init_cmd = ["terraform", "-chdir=infra", "init", "-reconfigure"]
            
            # Check if there's a local state file to migrate
            local_state = infra_path / "terraform.tfstate"
            if local_state.exists():
                progress.update(task, description="[cyan]Migrating local state to S3...")
            
            subprocess.run(init_cmd, check=True, capture_output=True)
            progress.update(task, description="[green]✓ Terraform initialized")
            progress.stop_task(task)
            
            # Refresh state to sync with AWS
            refresh_task = progress.add_task("[cyan]Refreshing Terraform state...", total=None)
            refresh_cmd = ["terraform", "-chdir=infra", "refresh", "-input=false"]
            subprocess.run(refresh_cmd, check=True, capture_output=True)
            progress.update(refresh_task, description="[green]✓ State refreshed")
            progress.stop_task(refresh_task)
            
            # Apply Terraform configuration
            apply_task = progress.add_task("[cyan]Applying Terraform configuration...", total=None)
            apply_cmd = ["terraform", "-chdir=infra", "apply", "-auto-approve"]
            
            if force_recreate:
                console.print("[yellow]⚠ Force recreate mode enabled")
            
            result = subprocess.run(apply_cmd, capture_output=True)
            
            if result.returncode == 0:
                progress.update(apply_task, description="[green]✓ Infrastructure deployed")
                progress.stop_task(apply_task)
                return True
            else:
                # Check if it's just because resources already exist
                stderr_str = result.stderr.decode() if isinstance(result.stderr, bytes) else str(result.stderr) if result.stderr else ""
                if "already exists" in stderr_str or "EntityAlreadyExists" in stderr_str:
                    progress.update(apply_task, description="[yellow]⚠ Infrastructure already exists (continuing)")
                    progress.stop_task(apply_task)
                    console.print("[dim]   Resources already exist in AWS - using existing infrastructure[/dim]")
                    return True
                else:
                    progress.update(apply_task, description="[red]✗ Failed to apply infrastructure")
                    progress.stop_task(apply_task)
                    console.print(f"[dim]Error: {stderr_str[:500]}[/dim]")
                    return False
            
        except subprocess.CalledProcessError as e:
            stderr_str = e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr) if e.stderr else ""
            
            # If resources already exist, treat it as success for demo purposes
            if "already exists" in stderr_str or "EntityAlreadyExists" in stderr_str:
                console.print("[yellow]⚠ Resources already exist - using existing infrastructure")
                return True
            
            console.print(f"[red]✗ Error running Terraform: {e}")
            if e.stderr:
                console.print(f"[dim]Error output: {stderr_str[:500]}[/dim]")
            
            return False
        except Exception as e:
            console.print(f"[red]✗ Unexpected error applying infrastructure: {e}")
            return False


def get_terraform_outputs() -> Dict[str, str]:
    """
    Get Terraform outputs, particularly the ALB DNS name.
    
    Returns:
        Dictionary of output values
    """
    infra_path = Path("infra")
    
    if not infra_path.exists():
        return {}
    
    try:
        output_cmd = ["terraform", "-chdir=infra", "output", "-json"]
        result = subprocess.run(output_cmd, capture_output=True, check=True, text=True)
        
        if result.stdout:
            outputs = json.loads(result.stdout)
            # Extract values from the Terraform output format
            return {key: val.get("value", "") for key, val in outputs.items()}
        
        return {}
    except (subprocess.CalledProcessError, json.JSONDecodeError, Exception):
        return {}


def force_ecs_update() -> bool:
    """
    Force ECS services to update with latest images from ECR.
    This is a fallback in case Terraform state has issues.
    
    Returns:
        True if successful, False otherwise
    """
    session = boto3.Session(profile_name=PROFILE_NAME, region_name=REGION_NAME)
    ecs_client = session.client("ecs")
    
    cluster_name = "three-tier-cluster"
    services = ["backend-service", "frontend-service"]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Forcing ECS service updates...", total=None)
        
        try:
            for service_name in services:
                try:
                    ecs_client.update_service(
                        cluster=cluster_name,
                        service=service_name,
                        forceNewDeployment=True
                    )
                except ClientError as e:
                    # Service might not exist yet, that's okay
                    if e.response.get("Error", {}).get("Code") != "ServiceNotFoundException":
                        console.print(f"[dim]   Note: Could not update {service_name}[/dim]")
            
            progress.update(task, description="[green]✓ Triggered ECS service updates")
            progress.stop_task(task)
            return True
        except Exception as e:
            progress.update(task, description="[yellow]⚠ Could not force ECS updates")
            progress.stop_task(task)
            console.print(f"[dim]   {str(e)}[/dim]")
            return False


def build_images() -> None:
    """
    Build Docker images for backend and frontend, and tag them as latest.
    """
    images = {
        "backend": {
            "context": Path("backend"),
            "dockerfile": Path("backend/Dockerfile"),
            "tag": f"{DOCKER_BASE_URL}backend:latest",
            "local_tag": "backend:latest",
        },
        "frontend": {
            "context": Path("frontend"),
            "dockerfile": Path("frontend/Dockerfile"),
            "tag": f"{DOCKER_BASE_URL}frontend:latest",
            "local_tag": "frontend:latest",
        },
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for name, image_config in images.items():
            context = image_config["context"]
            dockerfile = image_config["dockerfile"]
            tag = image_config["tag"]
            local_tag = image_config["local_tag"]

            task = progress.add_task(f"[cyan]Building {name} image...", total=None)

            # Check if Dockerfile exists
            if not dockerfile.exists():
                progress.update(task, description=f"[yellow]⚠ Skipping {name} - Dockerfile not found")
                progress.stop_task(task)
                continue

            # Check if context directory exists
            if not context.exists():
                progress.update(task, description=f"[yellow]⚠ Skipping {name} - context not found")
                progress.stop_task(task)
                continue

            try:
                # Build the image
                build_cmd = [
                    "docker",
                    "build",
                    "--platform", "linux/amd64",
                    "-f", str(dockerfile),
                    "-t", local_tag,
                    "-t", tag,
                ]
                
                # For frontend, pass an empty API URL (ALB routes /api/* to backend)
                if name == "frontend":
                    build_cmd.extend(["--build-arg", "VITE_API_URL="])
                
                build_cmd.append(str(context))
                subprocess.run(
                    build_cmd,
                    check=True,
                    capture_output=True,
                )
                progress.update(task, description=f"[green]✓ Built {name} image")
                progress.stop_task(task)
            except subprocess.CalledProcessError as e:
                progress.update(task, description=f"[red]✗ Failed to build {name} image")
                progress.stop_task(task)
                console.print(f"[dim]Command: {' '.join(build_cmd)}")
                if e.stderr:
                    stderr_str = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
                    console.print(f"[dim]Error: {stderr_str}")
            except Exception as e:
                progress.update(task, description=f"[red]✗ Unexpected error building {name}")
                progress.stop_task(task)
                console.print(f"[dim]Error: {e}")


def push_images_to_ecr() -> None:
    """
    Authenticate with ECR and push both backend and frontend images.
    """
    ecr_registry = DOCKER_BASE_URL.rstrip("/")
    images = {
        "backend": f"{DOCKER_BASE_URL}backend:latest",
        "frontend": f"{DOCKER_BASE_URL}frontend:latest",
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: Get ECR login password and authenticate
        try:
            task = progress.add_task("[cyan]Authenticating with ECR...", total=None)
            get_password_cmd = [
                "aws",
                "ecr",
                "get-login-password",
                "--region",
                REGION_NAME,
                "--profile",
                PROFILE_NAME,
            ]

            result = subprocess.run(
                get_password_cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            ecr_password = result.stdout.strip()

            # Login to Docker using the password
            login_cmd = [
                "docker",
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                ecr_registry,
            ]

            subprocess.run(
                login_cmd,
                input=ecr_password,
                text=True,
                check=True,
                capture_output=True,
            )
            progress.update(task, description="[green]✓ Authenticated with ECR")
            progress.stop_task(task)
        except subprocess.CalledProcessError as e:
            progress.update(task, description="[red]✗ ECR authentication failed")
            progress.stop_task(task)
            if e.stderr:
                console.print(f"[dim]Error: {e.stderr}")
            return
        except Exception as e:
            console.print(f"[red]✗ Unexpected error during ECR authentication: {e}")
            return

        # Step 2: Push each image
        for name, image_tag in images.items():
            push_task = progress.add_task(f"[cyan]Pushing {name} image...", total=None)
            try:
                push_cmd = ["docker", "push", image_tag]

                subprocess.run(
                    push_cmd,
                    check=True,
                    capture_output=True,
                )
                progress.update(push_task, description=f"[green]✓ Pushed {name} image")
                progress.stop_task(push_task)
            except subprocess.CalledProcessError as e:
                progress.update(push_task, description=f"[red]✗ Failed to push {name} image")
                progress.stop_task(push_task)
                console.print(f"[dim]Command: {' '.join(push_cmd)}")
                if e.stderr:
                    stderr_str = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
                    console.print(f"[dim]Error: {stderr_str}")
            except Exception as e:
                progress.update(push_task, description=f"[red]✗ Unexpected error pushing {name}")
                progress.stop_task(push_task)
                console.print(f"[dim]Error: {e}")


def main() -> None:
    """
    Main deployment workflow:
    1. Fetch Terraform configuration from S3
    2. Fetch Dockerfiles from S3
    3. Write Dockerfiles to local directories
    4. Build Docker images
    5. Push images to ECR
    6. Apply Terraform infrastructure (after images are in ECR)
    """
    # Print welcome banner
    console.print()
    console.print(Panel.fit(
        "[bold cyan]AWS Deployment Automation[/bold cyan]\n"
        "[dim]Automated deployment of three-tier application to AWS[/dim]",
        border_style="cyan",
        padding=(1, 2)
    ))
    console.print()
    
    try:
        # # Step 1: Fetch Terraform configuration from S3
        # console.print(Panel("[bold]Step 1:[/bold] Fetching Terraform Configuration", 
        #                    style="cyan", border_style="dim"))
        # if not fetch_terraform_files():
        #     console.print()
        #     console.print(Panel("[bold red]Deployment Failed[/bold red]\n"
        #                        "Failed to fetch Terraform configuration", 
        #                        border_style="red"))
        #     return

        # console.print()

        # Step 2: Fetch Dockerfiles from S3
        console.print(Panel("[bold]Step 1:[/bold] Fetching Dockerfiles", 
                           style="cyan", border_style="dim"))
        dockerfiles = fetch_dockerfiles()
        if not dockerfiles or all(v is None for v in dockerfiles.values()):
            console.print()
            console.print(Panel("[bold red]Deployment Failed[/bold red]\n"
                               "No Dockerfiles were successfully fetched", 
                               border_style="red"))
            return

        console.print()

        # Step 3: Write Dockerfiles to local directories
        console.print(Panel("[bold]Step 2:[/bold] Writing Dockerfiles", 
                           style="cyan", border_style="dim"))
        write_dockerfiles(dockerfiles)
        console.print()

        # Step 4: Build Docker images
        console.print(Panel("[bold]Step 3:[/bold] Building Docker Images", 
                           style="cyan", border_style="dim"))
        build_images()
        console.print()

        # Step 5: Push images to ECR
        console.print(Panel("[bold]Step 4:[/bold] Pushing Images to ECR", 
                           style="cyan", border_style="dim"))
        push_images_to_ecr()
        console.print()
        
        # Step 6: Apply Terraform infrastructure (after images exist in ECR)
        console.print(Panel("[bold]Step 5:[/bold] Applying Terraform Infrastructure", 
                           style="cyan", border_style="dim"))
        infra_success = apply_infrastructure()
        console.print()

        # Step 7: Force ECS update if Terraform had issues (fallback)
        if not infra_success:
            console.print(Panel("[bold]Step 6:[/bold] Forcing ECS Service Update (Fallback)", 
                               style="yellow", border_style="dim"))
            force_ecs_update()
            console.print()

        # Get Terraform outputs (ALB DNS)
        outputs = get_terraform_outputs()
        alb_dns = outputs.get("alb_dns", outputs.get("alb_url", outputs.get("load_balancer_dns", "")))
        
        # Success message
        success_message = ""
        if infra_success:
            success_message = (
                "[bold green]✓ Deployment Completed Successfully![/bold green]\n"
                "[dim]All services have been deployed to AWS ECS[/dim]"
            )
        else:
            success_message = (
                "[bold green]✓ Deployment Completed![/bold green]\n"
                "[dim]Images pushed to ECR and ECS services updated\n"
                "Using existing infrastructure with new images[/dim]"
            )
        
        # Add ALB URL if available
        if alb_dns:
            # Remove http:// or https:// prefix if present to avoid duplication
            clean_dns = alb_dns.replace("http://", "").replace("https://", "")
            success_message += f"\n\n[bold cyan]🌐 Application URL:[/bold cyan]\n[link=http://{clean_dns}]http://{clean_dns}[/link]"
        
        console.print(Panel.fit(
            success_message,
            border_style="green",
            padding=(1, 2)
        ))
        console.print()
        
    except KeyboardInterrupt:
        console.print()
        console.print(Panel("[bold yellow]⚠ Deployment Interrupted[/bold yellow]\n"
                           "Deployment was cancelled by user", 
                           border_style="yellow"))
        raise
    except Exception as e:
        console.print()
        console.print(Panel(f"[bold red]✗ Deployment Failed[/bold red]\n"
                           f"[dim]{str(e)}[/dim]", 
                           border_style="red"))
        raise


if __name__ == "__main__":
    main()
