# TODO: each of these steps should be displayed distinctly in the MCP tool (esp the terminal commands for docker build)
# TODO: review system design with Andrew tmrw
import subprocess
from pathlib import Path
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError

# TODO: set up .env for these?
PROFILE_NAME = "automate-deployment"
REGION_NAME = "us-east-2"
BUCKET_NAME = "three-tier-dockerfiles"
DOCKER_BASE_URL = "358262661502.dkr.ecr.us-east-2.amazonaws.com/"

# step 1: fetch dockerfiles from s3
# step 2: build both docker images
# step 3: push both images to ECR
# step 4: TBD


def fetch_dockerfiles() -> Dict[str, Optional[str]]:
    session = boto3.Session(profile_name=PROFILE_NAME, region_name=REGION_NAME)
    s3_client = session.client("s3")

    dockerfiles = {}
    paths = {"backend": "backend/Dockerfile", "frontend": "frontend/Dockerfile"}

    for name, s3_key in paths.items():
        try:
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
            dockerfile_content = response["Body"].read().decode("utf-8")
            dockerfiles[name] = dockerfile_content
            print(f"✅ Successfully fetched {name} Dockerfile from s3://{BUCKET_NAME}/{s3_key}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                print(f"⚠️  Dockerfile not found at s3://{BUCKET_NAME}/{s3_key}")
            else:
                print(f"❌ Error fetching {name} Dockerfile: {e}")
            dockerfiles[name] = None

    return dockerfiles


def write_dockerfiles(dockerfiles: Dict[str, Optional[str]]) -> None:
    local_paths = {
        "backend": Path("backend/Dockerfile"),
        "frontend": Path("frontend/Dockerfile"),
    }

    for name, content in dockerfiles.items():
        if content is None:
            print(f"⚠️  Skipping {name} Dockerfile - content not available")
            continue

        local_path = local_paths.get(name)
        if not local_path:
            print(f"⚠️  No local path defined for {name} Dockerfile")
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
            print(f"✅ Successfully saved {name} Dockerfile to {local_path}")
        except Exception as e:
            print(f"❌ Error writing {name} Dockerfile to {local_path}: {e}")


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

    for name, image_config in images.items():
        context = image_config["context"]
        dockerfile = image_config["dockerfile"]
        tag = image_config["tag"]
        local_tag = image_config["local_tag"]

        # Check if Dockerfile exists
        if not dockerfile.exists():
            print(f"⚠️  Dockerfile not found at {dockerfile}, skipping {name} build")
            continue

        # Check if context directory exists
        if not context.exists():
            print(f"⚠️  Context directory not found at {context}, skipping {name} build")
            continue

        try:
            # Build the image
            print(f"🔨 Building {name} Docker image...")
            build_cmd = [
                "docker",
                "build",
                "--platform", "linux/amd64",
                "-f", str(dockerfile),
                "-t", local_tag,
                "-t", tag,
                str(context),
            ]
            subprocess.run(
                build_cmd,
                check=True,
            )
            print(f"✅ Successfully built {name} image")
            print(f"   Tagged as: {local_tag}")
            print(f"   Tagged as: {tag}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error building {name} image: {e}")
            print(f"   Command: {' '.join(build_cmd)}")
            if e.stderr:
                print(f"   Error output: {e.stderr}")
        except Exception as e:
            print(f"❌ Unexpected error building {name} image: {e}")


def push_images_to_ecr() -> None:
    """
    Authenticate with ECR and push both backend and frontend images.
    """
    ecr_registry = DOCKER_BASE_URL.rstrip("/")
    images = {
        "backend": f"{DOCKER_BASE_URL}backend:latest",
        "frontend": f"{DOCKER_BASE_URL}frontend:latest",
    }

    # Step 1: Get ECR login password and authenticate
    try:
        print(f"🔐 Authenticating with ECR registry: {ecr_registry}")
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
        print("✅ Successfully authenticated with ECR")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error authenticating with ECR: {e}")
        if e.stderr:
            print(f"   Error output: {e.stderr}")
        return
    except Exception as e:
        print(f"❌ Unexpected error during ECR authentication: {e}")
        return

    # Step 2: Push each image
    for name, image_tag in images.items():
        try:
            print(f"📤 Pushing {name} image to ECR...")
            push_cmd = ["docker", "push", image_tag]

            subprocess.run(
                push_cmd,
                check=True,
            )
            print(f"✅ Successfully pushed {name} image: {image_tag}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error pushing {name} image: {e}")
            print(f"   Command: {' '.join(push_cmd)}")
            if e.stderr:
                print(f"   Error output: {e.stderr}")
        except Exception as e:
            print(f"❌ Unexpected error pushing {name} image: {e}")


# TODO: hook this up to the deploy mcp function
def main() -> None:
    """
    Main deployment workflow:
    1. Fetch Dockerfiles from S3
    2. Write Dockerfiles to local directories
    3. Build Docker images
    4. Push images to ECR
    """
    try:
        # Step 1: Fetch Dockerfiles from S3
        print("\n📥 Step 1: Fetching Dockerfiles from S3...")
        dockerfiles = fetch_dockerfiles()
        if not dockerfiles or all(v is None for v in dockerfiles.values()):
            print("❌ No Dockerfiles were successfully fetched. Aborting deployment.")
            return

        # Step 2: Write Dockerfiles to local directories
        print("\n💾 Step 2: Writing Dockerfiles to local directories...")
        write_dockerfiles(dockerfiles)

        # Step 3: Build Docker images
        print("\n🔨 Step 3: Building Docker images...")
        build_images()

        # Step 4: Push images to ECR
        print("\n📤 Step 4: Pushing images to ECR...")
        push_images_to_ecr()

        print("\n" + "=" * 80)
        print("✅ Deployment process completed successfully!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Deployment interrupted by user")
        raise
    except Exception as e:
        print(f"\n\n❌ Deployment failed with unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
