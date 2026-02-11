#!/usr/bin/env python3
"""
AAC Assistant 2.0 - Model Download Script
Downloads all required models for offline use
"""

import platform
import subprocess
import sys
from pathlib import Path

from loguru import logger


def check_ollama_installed():
    """Check if Ollama is installed"""
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"Ollama found: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    return False


def install_ollama():
    """Install Ollama based on platform"""
    system = platform.system().lower()

    logger.info(f"Installing Ollama for {system}")

    if system == "windows":
        logger.info("Please install Ollama manually from: https://ollama.ai/download")
        logger.info("1. Download the Windows installer")
        logger.info("2. Run the installer")
        logger.info("3. Return here to continue")
        input("Press Enter when Ollama is installed...")

    elif system == "darwin":  # macOS
        try:
            # Download install script safely
            result = subprocess.run(
                ["curl", "-fsSL", "https://ollama.ai/install.sh"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Execute with sh (safer than shell=True)
            subprocess.run(["sh", "-c", result.stdout], check=True)
        except subprocess.CalledProcessError:
            logger.error(
                "Failed to install Ollama. Please install manually from https://ollama.ai"
            )
            return False

    else:  # Linux and others
        try:
            # Download install script safely
            result = subprocess.run(
                ["curl", "-fsSL", "https://ollama.ai/install.sh"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Execute with sh (safer than shell=True)
            subprocess.run(["sh", "-c", result.stdout], check=True)
        except subprocess.CalledProcessError:
            logger.error(
                "Failed to install Ollama. Please install manually from https://ollama.ai"
            )
            return False

    return check_ollama_installed()


def download_whisper_model():
    """Download Whisper model"""
    logger.info("📥 Downloading Whisper speech recognition model...")

    try:
        import whisper

        # Download small model (recommended balance of size/speed/accuracy)
        logger.info("Downloading Whisper 'small' model (244MB)...")
        model = whisper.load_model("small")

        logger.success("✅ Whisper model downloaded successfully!")
        return True

    except ImportError:
        logger.error(
            "❌ Whisper not installed. Install with: pip install openai-whisper"
        )
        return False
    except Exception as e:
        logger.error(f"❌ Failed to download Whisper model: {e}")
        return False


def download_sentence_transformers_model():
    """Download Sentence Transformers model"""
    logger.info("📥 Downloading Sentence Transformers embedding model...")

    try:
        from sentence_transformers import SentenceTransformer

        # Download all-MiniLM-L6-v2 model (80MB, good balance)
        logger.info("Downloading 'all-MiniLM-L6-v2' model (80MB)...")
        model = SentenceTransformer("all-MiniLM-L6-v2")

        logger.success("✅ Sentence Transformers model downloaded successfully!")
        return True

    except ImportError:
        logger.error(
            "❌ Sentence Transformers not installed. Install with: pip install sentence-transformers"
        )
        return False
    except Exception as e:
        logger.error(f"❌ Failed to download Sentence Transformers model: {e}")
        return False


def pull_ollama_model(model_name: str = "qwen:7b-q4_0"):
    """Pull Ollama model"""
    logger.info(f"📥 Pulling Ollama model: {model_name}")

    try:
        # Check if Ollama is running
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            logger.error("❌ Ollama is not running. Please start Ollama first.")
            return False

        # Pull the model
        logger.info(
            "This may take 10-30 minutes depending on your internet connection..."
        )
        result = subprocess.run(
            ["ollama", "pull", model_name], capture_output=True, text=True
        )

        if result.returncode == 0:
            logger.success(f"✅ Ollama model '{model_name}' pulled successfully!")
            return True
        else:
            logger.error(f"❌ Failed to pull Ollama model: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("❌ Ollama pull timed out. Please try again.")
        return False
    except FileNotFoundError:
        logger.error("❌ Ollama command not found. Please install Ollama first.")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to pull Ollama model: {e}")
        return False


def download_arasaac_symbols():
    """Download sample AAC symbols from ARASAAC"""
    logger.info("📥 Downloading sample AAC symbols...")

    try:
        # Create symbols directory
        symbols_dir = Path("data/symbols")
        symbols_dir.mkdir(parents=True, exist_ok=True)

        # Download sample symbols (this is a simplified example)
        # In a real implementation, you'd download from ARASAAC API
        logger.info("Creating sample symbol files...")

        # Create sample symbol metadata
        sample_symbols = [
            {
                "label": "cow",
                "description": "A farm animal that gives milk",
                "category": "farm_animals",
            },
            {
                "label": "horse",
                "description": "A large animal you can ride",
                "category": "farm_animals",
            },
            {
                "label": "chicken",
                "description": "A bird that lays eggs",
                "category": "farm_animals",
            },
            {"label": "apple", "description": "A red fruit", "category": "food"},
            {
                "label": "water",
                "description": "Clear liquid for drinking",
                "category": "drinks",
            },
        ]

        # Create symbol metadata file
        import json

        with open(symbols_dir / "symbols_metadata.json", "w") as f:
            json.dump(sample_symbols, f, indent=2)

        logger.success("✅ Sample symbols created successfully!")
        return True

    except ImportError:
        logger.warning("⚠️  requests not available. Skipping symbol download.")
        return True  # Not critical for basic functionality
    except Exception as e:
        logger.error(f"❌ Failed to download symbols: {e}")
        return False


def check_python_version():
    """Check Python version compatibility"""
    if sys.version_info < (3, 8):
        logger.error("❌ Python 3.8 or higher is required")
        return False
    logger.info(f"✅ Python version: {sys.version}")
    return True


def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        "sqlalchemy",
        "torch",
        "transformers",
        "sentence-transformers",
        "openai-whisper",
        "faiss-cpu",
        "pyttsx3",
        "sounddevice",
        "soundfile",
        "webrtcvad",
        "loguru",
        "pydantic",
        "pyyaml",
        "pillow",
        "httpx",
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            logger.debug(f"✅ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            logger.warning(f"⚠️  {package} is not installed")

    if missing_packages:
        logger.error(f"❌ Missing packages: {', '.join(missing_packages)}")
        logger.info("Install missing packages with:")
        logger.info(f"pip install {' '.join(missing_packages)}")
        return False

    logger.success("✅ All required packages are installed!")
    return True


def main():
    """Main setup function"""
    logger.info("🚀 Starting AAC Assistant 2.0 model download...")
    logger.info("This script will download all required models for offline use.")

    # Check Python version
    if not check_python_version():
        return False

    # Check dependencies
    if not check_dependencies():
        response = input("Some packages are missing. Continue anyway? (y/N): ")
        if response.lower() != "y":
            return False

    success = True

    # Check and install Ollama
    if not check_ollama_installed():
        logger.warning("Ollama not found. Attempting to install...")
        if not install_ollama():
            logger.error("Failed to install Ollama. Please install manually.")
            success = False

    # Download models
    logger.info("\n" + "=" * 50)
    logger.info("Downloading AI models...")
    logger.info("=" * 50)

    # Download Whisper model
    if not download_whisper_model():
        success = False

    # Download Sentence Transformers model
    if not download_sentence_transformers_model():
        success = False

    # Download Ollama model (this requires Ollama to be running)
    logger.info("\n" + "=" * 50)
    logger.info("Starting Ollama service...")
    logger.info("=" * 50)

    logger.info("Please make sure Ollama is running before continuing.")
    logger.info("If Ollama is not running, start it with: ollama serve")
    logger.info("Then press Enter to continue...")
    input()

    if check_ollama_installed():
        # Pull recommended model
        if not pull_ollama_model("qwen:7b-q4_0"):
            logger.warning("Failed to pull qwen:7b-q4_0, trying smaller model...")
            if not pull_ollama_model("qwen:1.8b-q4_0"):
                success = False
    else:
        logger.error("Ollama is not available. Skipping LLM model download.")
        success = False

    # Download symbols
    if not download_arasaac_symbols():
        logger.warning(
            "Symbol download failed, but this is not critical for basic functionality."
        )

    # Final summary
    logger.info("\n" + "=" * 50)
    if success:
        logger.success("✅ Model download completed successfully!")
        logger.info("AAC Assistant 2.0 is now ready for offline use.")
        logger.info("You can now run the backend server.")
    else:
        logger.warning("⚠️  Model download completed with some issues.")
        logger.info("Some features may be limited, but the app should still work.")

    logger.info("\nTo start the application:")
    logger.info("1. Start the backend: start.bat")
    logger.info("2. Start the frontend: cd src/frontend && npm run dev")
    logger.info("=" * 50)

    return success


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    )

    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\nDownload interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
