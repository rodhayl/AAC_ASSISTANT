"""
AAC Assistant GUI Launcher
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import socket
import os
import sys
import time
import re
import shutil
import functools
import ctypes
import logging

# PyInstaller Splash Screen support
try:
    import pyi_splash
except ImportError:
    pyi_splash = None

# Imports for frozen exe mode are now lazy-loaded inside _start_services_frozen
# to ensure the GUI appears as fast as possible.


def load_config(base_dir):
    """Load configuration from env.properties file."""
    config = {
        'BACKEND_HOST': '0.0.0.0',
        'BACKEND_PORT': '8086',
        'FRONTEND_PORT': '5176',
    }
    config_file = os.path.join(base_dir, 'env.properties')
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config


def get_python_exe():
    """Get python.exe path (not pythonw.exe)."""
    exe = sys.executable
    if exe.endswith('pythonw.exe'):
        exe = exe.replace('pythonw.exe', 'python.exe')
    return exe


class AACLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("AAC Assistant")
        self.root.geometry("380x520")  # Slightly taller for progress bar
        self.root.resizable(False, False)
        
        self.is_frozen = getattr(sys, 'frozen', False)
        self.api_thread = None
        self.server_should_exit = False
        self.uvicorn_server = None  # For graceful shutdown
        
        self.backend_process = None
        self.frontend_process = None
        self.backend_log_file = None
        self.frontend_log_file = None
        
        # For frozen builds, use the exe's directory
        if self.is_frozen:
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.frontend_dir = os.path.join(self.base_dir, "src", "frontend")
        
        # Load configuration from env.properties
        config = load_config(self.base_dir)
        self.backend_host = config.get('BACKEND_HOST', '0.0.0.0')
        self.backend_port = int(config.get('BACKEND_PORT', '8086'))
        self.frontend_port = int(config.get('FRONTEND_PORT', '5176'))
        
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.start_status_checker()
        # Initial voice/STT dependency status
        self.update_voice_status()
        
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="AAC Assistant", font=("Segoe UI", 14, "bold")).pack(pady=(0, 15))
        
        # Status indicators
        status_frame = ttk.LabelFrame(main_frame, text="Service Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Backend Status
        b_row = ttk.Frame(status_frame)
        b_row.pack(fill=tk.X, pady=2)
        self.backend_port_label = ttk.Label(b_row, text=f"Backend (:{self.backend_port}):")
        self.backend_port_label.pack(side=tk.LEFT)
        self.backend_status = ttk.Label(b_row, text="Stopped", foreground="red")
        self.backend_status.pack(side=tk.RIGHT)
        
        # Frontend Status
        f_row = ttk.Frame(status_frame)
        f_row.pack(fill=tk.X, pady=2)
        
        frontend_label_text = f"Frontend (:{self.frontend_port}):"
        if self.is_frozen:
           frontend_label_text = "Frontend (Integrated):"
           
        self.frontend_port_label = ttk.Label(f_row, text=frontend_label_text)
        self.frontend_port_label.pack(side=tk.LEFT)
        self.frontend_status = ttk.Label(f_row, text="Stopped", foreground="red")
        self.frontend_status.pack(side=tk.RIGHT)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(btn_frame, text="Start Services", command=self.start_services)
        self.start_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        
        self.stop_button = ttk.Button(btn_frame, text="Stop Services", command=self.stop_services, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        # Force stop button - kills ANY process on configured ports
        btn_frame2 = ttk.Frame(main_frame)
        btn_frame2.pack(fill=tk.X, pady=(0, 10))
        
        self.force_stop_button = ttk.Button(
            btn_frame2, 
            text="Force Stop Ports", 
            command=self.force_stop_ports
        )
        self.force_stop_button.pack(fill=tk.X)

        # Startup Progress (shown only during startup)
        self.progress_frame = ttk.LabelFrame(main_frame, text="Startup Progress", padding="10")
        # Don't pack initially - only show during startup
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, 
            mode='indeterminate',
            length=320
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.progress_label = ttk.Label(
            self.progress_frame, 
            text="Ready to start...",
            wraplength=320
        )
        self.progress_label.pack(anchor='w')

        # Voice / STT dependency status
        voice_frame = ttk.LabelFrame(main_frame, text="Voice / STT Status", padding="10")
        voice_frame.pack(fill=tk.X, pady=(0, 10))

        ff_row = ttk.Frame(voice_frame)
        ff_row.pack(fill=tk.X, pady=2)
        ttk.Label(ff_row, text="ffmpeg:").pack(side=tk.LEFT)
        self.ffmpeg_status = ttk.Label(ff_row, text="Checking...", foreground="gray")
        self.ffmpeg_status.pack(side=tk.RIGHT)

        whisper_row = ttk.Frame(voice_frame)
        whisper_row.pack(fill=tk.X, pady=2)
        ttk.Label(whisper_row, text="Whisper (openai-whisper):").pack(side=tk.LEFT)
        self.whisper_status = ttk.Label(whisper_row, text="Checking...", foreground="gray")
        self.whisper_status.pack(side=tk.RIGHT)

        sd_row = ttk.Frame(voice_frame)
        sd_row.pack(fill=tk.X, pady=2)
        ttk.Label(sd_row, text="sounddevice (mic):").pack(side=tk.LEFT)
        self.sounddevice_status = ttk.Label(sd_row, text="Checking...", foreground="gray")
        self.sounddevice_status.pack(side=tk.RIGHT)

        sf_row = ttk.Frame(voice_frame)
        sf_row.pack(fill=tk.X, pady=2)
        ttk.Label(sf_row, text="soundfile (mic):").pack(side=tk.LEFT)
        self.soundfile_status = ttk.Label(sf_row, text="Checking...", foreground="gray")
        self.soundfile_status.pack(side=tk.RIGHT)

        vad_row = ttk.Frame(voice_frame)
        vad_row.pack(fill=tk.X, pady=2)
        ttk.Label(vad_row, text="webrtcvad (optional):").pack(side=tk.LEFT)
        self.vad_status = ttk.Label(vad_row, text="Checking...", foreground="gray")
        self.vad_status.pack(side=tk.RIGHT)

        # Inline guidance shown when something is missing
        self.voice_help = ttk.Label(
            voice_frame,
            text="",
            foreground="gray",
            wraplength=320,
            justify="left",
        )
        self.voice_help.pack(anchor="w", pady=(4, 0))

        self.link_voice_help = ttk.Label(voice_frame, text="How to install voice support", foreground="blue", cursor="hand2")
        self.link_voice_help.pack(anchor="w", pady=(6, 0))
        self.link_voice_help.bind(
            "<Button-1>",
            lambda e: self.open_url("https://github.com/openai/whisper#installation"),
        )
        
        # Quick links
        links_frame = ttk.LabelFrame(main_frame, text="Quick Links", padding="10")
        links_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.link_frontend = ttk.Label(links_frame, text="Open Frontend", foreground="blue", cursor="hand2")
        self.link_frontend.pack(anchor="w", pady=1)
        
        frontend_url = f"http://localhost:{self.frontend_port}"
        if self.is_frozen:
            frontend_url = f"http://localhost:{self.backend_port}"
            
        self.link_frontend.bind("<Button-1>", lambda e: self.open_url(frontend_url))
        
        self.link_api = ttk.Label(links_frame, text="Open API Docs", foreground="blue", cursor="hand2")
        self.link_api.pack(anchor="w", pady=1)
        self.link_api.bind("<Button-1>", lambda e: self.open_url(f"http://localhost:{self.backend_port}/docs"))
        
        link_logs = ttk.Label(links_frame, text="Open Logs Folder", foreground="blue", cursor="hand2")
        link_logs.pack(anchor="w", pady=1)
        link_logs.bind("<Button-1>", lambda e: self.open_logs_folder())
        
        # Status bar
        self.status_bar = ttk.Label(main_frame, text="Ready", relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def update_voice_status(self):
        """Check ffmpeg, Whisper, and audio helper libraries for UI status."""
        missing_notes = []

        # ffmpeg
        ffmpeg_path = shutil.which("ffmpeg")
        ffmpeg_ok = ffmpeg_path is not None
        if ffmpeg_ok:
            self.ffmpeg_status.config(text="Installed", foreground="green")
        else:
            self.ffmpeg_status.config(text="Missing", foreground="red")
            missing_notes.append(
                "- FFMPEG MISSING: Please install FFmpeg for Windows.\n"
                "  1. Download from https://www.ffmpeg.org/download.html\n"
                "  2. Extract to C:\\ffmpeg\n"
                "  3. Add C:\\ffmpeg\\bin to your System PATH environment variable.\n"
                "  4. Restart this application."
            )

        # openai-whisper (whisper module)
        try:
            import whisper  # type: ignore
            whisper_ok = True
        except Exception:
            whisper_ok = False

        if whisper_ok:
            self.whisper_status.config(text="Installed", foreground="green")
        else:
            self.whisper_status.config(text="Missing", foreground="red")
            missing_notes.append(
                "- Install openai-whisper with: pip install -U openai-whisper, then rerun start.bat."
            )

        # sounddevice (microphone input)
        try:
            import sounddevice  # type: ignore  # noqa: F401
            sd_ok = True
        except Exception:
            sd_ok = False

        if sd_ok:
            self.sounddevice_status.config(text="Installed", foreground="green")
        else:
            self.sounddevice_status.config(text="Missing", foreground="red")
            missing_notes.append(
                "- sounddevice is not installed. Microphone input will not work. "
                "Install with: pip install sounddevice"
            )

        # soundfile (saving recorded audio)
        try:
            import soundfile  # type: ignore  # noqa: F401
            sf_ok = True
        except Exception:
            sf_ok = False

        if sf_ok:
            self.soundfile_status.config(text="Installed", foreground="green")
        else:
            self.soundfile_status.config(text="Missing", foreground="red")
            missing_notes.append(
                "- soundfile is not installed. Microphone input will not work. "
                "Install with: pip install soundfile"
            )

        # webrtcvad (optional VAD)
        try:
            # Suppress the known pkg_resources deprecation UserWarning that
            # can be emitted when importing webrtcvad (coming from its
            # use of pkg_resources). We only suppress that specific warning
            # so other important warnings are preserved.
            import warnings as _warnings
            with _warnings.catch_warnings():
                _warnings.filterwarnings(
                    "ignore",
                    message="pkg_resources is deprecated as an API",
                    category=UserWarning,
                )
                import webrtcvad  # type: ignore  # noqa: F401
            vad_ok = True
        except Exception:
            vad_ok = False

        if vad_ok:
            self.vad_status.config(text="Installed", foreground="green")
        else:
            self.vad_status.config(text="Missing", foreground="orange")
            missing_notes.append(
                "- webrtcvad is not installed (optional). Continuous listening will use simpler detection. "
                "Install with: pip install webrtcvad (may require MS C++ Build Tools)."
            )

        # Summary help text
        if not ffmpeg_ok or not whisper_ok:
            help_text = "Voice input is not fully set up:\n" + "\n".join(missing_notes)
            self.voice_help.config(text=help_text, foreground="red")
            
            if not ffmpeg_ok:
                self.link_voice_help.config(text="Download FFmpeg (Required)", foreground="blue")
                self.link_voice_help.bind(
                    "<Button-1>",
                    lambda e: self.open_url("https://www.ffmpeg.org/download.html"),
                )
            else:
                self.link_voice_help.config(text="How to install voice support", foreground="blue")
                self.link_voice_help.bind(
                    "<Button-1>",
                    lambda e: self.open_url("https://github.com/openai/whisper#installation"),
                )
        else:
            self.link_voice_help.config(text="How to install voice support", foreground="blue")
            self.link_voice_help.bind(
                "<Button-1>",
                lambda e: self.open_url("https://github.com/openai/whisper#installation"),
            )

            if sd_ok and sf_ok:
                # All required for mic input; VAD may be missing but is optional
                if vad_ok:
                    summary = (
                        "Voice input is ready (ffmpeg, Whisper, microphone, and VAD dependencies are installed)."
                    )
                else:
                    summary = (
                        "Voice input is ready for microphone and file uploads "
                        "(ffmpeg, Whisper, sounddevice, soundfile). VAD (webrtcvad) is optional."
                    )
                self.voice_help.config(text=summary, foreground="green")
            else:
                summary = (
                    "Transcription from audio files is ready (ffmpeg + Whisper). "
                    "Install sounddevice and soundfile to enable microphone input.\n"
                    + "\n".join(missing_notes)
                )
                self.voice_help.config(text=summary, foreground="orange")
    
    def find_free_port(self, start_port):
        """Find the first free port starting from start_port."""
        port = start_port
        while port < 65535:
            if not self.is_port_open(port):
                return port
            port += 1
        return start_port

    def is_port_open(self, port):
        """Check if a port is accepting connections (IPv4 or IPv6)."""
        for family, host in [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')]:
            try:
                with socket.socket(family, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    s.connect((host, port))
                    return True
            except:
                continue
        return False
    
    def start_status_checker(self):
        """Background status checker."""
        def checker():
            while True:
                try:
                    backend_up = self.is_port_open(self.backend_port)
                    backend_up = self.is_port_open(self.backend_port)
                    if self.is_frozen:
                        # In frozen mode, frontend is served by backend
                        frontend_up = backend_up
                    else:
                        frontend_up = self.is_port_open(self.frontend_port)
                        
                    if self.root.winfo_exists():
                        self.root.after(0, lambda b=backend_up, f=frontend_up: self.update_status_ui(b, f))
                    else:
                        break
                except Exception as e:
                    # Fail silently but don't kill the thread
                    try:
                        logs_dir = os.path.join(self.base_dir, "logs")
                        os.makedirs(logs_dir, exist_ok=True)
                        with open(os.path.join(logs_dir, "launcher_error.log"), "a") as f:
                            import datetime
                            f.write(f"{datetime.datetime.now()}: Checker error: {e}\n")
                    except:
                        pass
                time.sleep(1.5)

        threading.Thread(target=checker, daemon=True).start()
    
    def update_status_ui(self, backend_up, frontend_up):
        """Update status labels."""
        self.backend_status.config(
            text="Running" if backend_up else "Stopped",
            foreground="green" if backend_up else "red"
        )
        self.frontend_status.config(
            text="Running" if frontend_up else "Stopped",
            foreground="green" if frontend_up else "red"
        )
        
        has_processes = self.backend_process or self.frontend_process or self.api_thread
        self.stop_button.config(state=tk.NORMAL if (backend_up or frontend_up or has_processes) else tk.DISABLED)
        
    def _start_services_frozen(self):
        """Start services in frozen mode (in-process backend, static frontend served by FastAPI)."""
        self.start_button.config(state=tk.DISABLED)
        self.status_bar.config(text="Starting internal server...")
        
        # Show progress frame and start animation
        self.progress_frame.pack(fill=tk.X, pady=(0, 10), before=self.root.nametowidget(self.root.winfo_children()[0]).winfo_children()[4])
        self.progress_bar.start(10)
        self.progress_label.config(text="Initializing...")
        
        def update_progress(text):
            """Update progress label safely from any thread"""
            self.root.after(0, lambda: self.progress_label.config(text=text))
        
        def hide_progress():
            """Hide progress bar after startup"""
            self.progress_bar.stop()
            self.progress_frame.pack_forget()
        
        def worker():
            try:
                update_progress("Creating directories...")
                os.makedirs(os.path.join(self.base_dir, "data"), exist_ok=True)
                os.makedirs(os.path.join(self.base_dir, "logs"), exist_ok=True)
                os.makedirs(os.path.join(self.base_dir, "uploads"), exist_ok=True)
                
                # Check if backend port is already in use
                if self.is_port_open(self.backend_port):
                    update_progress("Checking port availability...")
                    # Try to determine who's using it
                    pids = self.find_pids_by_port(self.backend_port)
                    if pids:
                        # Ask user what to do
                        def ask_user():
                            result = messagebox.askyesnocancel(
                                "Port Conflict",
                                f"Port {self.backend_port} is already in use.\n\n"
                                f"Yes = Force stop existing process and start\n"
                                f"No = Use next available port\n"
                                f"Cancel = Abort startup"
                            )
                            return result
                        
                        # Run dialog in main thread
                        result_holder = [None]
                        event = threading.Event()
                        def do_ask():
                            result_holder[0] = ask_user()
                            event.set()
                        self.root.after(0, do_ask)
                        event.wait(timeout=60)
                        result = result_holder[0]
                        
                        if result is None:  # Cancel or timeout
                            self.root.after(0, lambda: self.status_bar.config(text="Startup cancelled"))
                            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                            self.root.after(0, hide_progress)
                            return
                        elif result:  # Yes - force stop
                            update_progress("Stopping existing process...")
                            for pid in pids:
                                self.kill_process(pid)
                            time.sleep(1)
                            # Verify port is now free
                            if self.is_port_open(self.backend_port):
                                self.root.after(0, lambda: messagebox.showerror(
                                    "Error", f"Could not free port {self.backend_port}"))
                                self.root.after(0, lambda: self.status_bar.config(text="Port conflict"))
                                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                                self.root.after(0, hide_progress)
                                return
                        else:  # No - find new port
                            new_port = self.find_free_port(self.backend_port + 1)
                            self.backend_port = new_port
                            self.root.after(0, lambda: self.backend_port_label.config(
                                text=f"Backend (:{self.backend_port}):"))
                    else:
                        # Port open but no PID found (maybe closing), wait briefly
                        time.sleep(2)
                        if self.is_port_open(self.backend_port):
                            # Still busy, find new port
                            new_port = self.find_free_port(self.backend_port + 1)
                            self.backend_port = new_port
                            self.root.after(0, lambda: self.backend_port_label.config(
                                text=f"Backend (:{self.backend_port}):"))
                
                update_progress("Loading application modules...")
                self.root.after(0, lambda: self.status_bar.config(text="Loading application..."))
                
                # Lazy import to speed up initial launch
                import uvicorn
                update_progress("Importing FastAPI application...")
                from src.api.main import app as fastapi_app
                
                # Create server config with proper shutdown support and explicit logging
                # using standard logging classes to avoid frozen mode import errors
                log_config = {
                    "version": 1,
                    "disable_existing_loggers": False,
                    "formatters": {
                        "default": {
                            "format": "%(asctime)s - %(levelname)s - %(message)s",
                            "datefmt": "%Y-%m-%d %H:%M:%S",
                        },
                        "access": {
                            "format": "%(asctime)s - %(levelname)s - %(client_addr)s - \"%(request_line)s\" %(status_code)s",
                            "datefmt": "%Y-%m-%d %H:%M:%S",
                        },
                    },
                    "handlers": {
                        "default": {
                            "formatter": "default",
                            "class": "logging.StreamHandler",
                            "stream": "ext://sys.stderr",
                        },
                        "access": {
                            "formatter": "access",
                            "class": "logging.StreamHandler",
                            "stream": "ext://sys.stdout",
                        },
                    },
                    "loggers": {
                        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                        "uvicorn.error": {"level": "INFO"},
                        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
                    },
                }

                update_progress("Configuring server...")
                config = uvicorn.Config(
                    fastapi_app, 
                    host=self.backend_host, 
                    port=self.backend_port,
                    log_level="info",
                    log_config=log_config
                )
                self.uvicorn_server = uvicorn.Server(config)
                
                update_progress("Starting server...")
                self.root.after(0, lambda: self.status_bar.config(text="Starting server..."))
                
                # Run server in this thread (it will block until shutdown)
                self.uvicorn_server.run()
                
            except Exception as e:
                # Ensure splash is closed so error dialog is visible
                if pyi_splash:
                    pyi_splash.close()
                    
                import traceback
                error_msg = f"Internal server failed: {e}"
                # Log to file for debugging
                try:
                    log_path = os.path.join(self.base_dir, "logs", "startup_error.log")
                    with open(log_path, "w") as f:
                        f.write(f"Error: {e}\n\n")
                        f.write(traceback.format_exc())
                except:
                    pass
                self.root.after(0, lambda: messagebox.showerror("Server Error", error_msg))
                self.root.after(0, lambda: self.status_bar.config(text="Server Error"))
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                self.root.after(0, hide_progress)

        self.api_thread = threading.Thread(target=worker, daemon=True)
        self.api_thread.start()
        
        # Monitor startup with timeout
        start_time = time.time()
        timeout_seconds = 60  # 1 minute for lazy loading mode (faster now)
        
        def check_startup():
            elapsed = time.time() - start_time
            if self.is_port_open(self.backend_port):
                hide_progress()
                self.root.after(0, lambda: self.status_bar.config(text="Services started (Internal)"))
                self.root.after(0, lambda: self.start_button.config(state=tk.DISABLED))
                self.root.after(0, lambda: self.stop_button.config(state=tk.NORMAL))
                # Update voice status after successful start
                self.root.after(0, self.update_voice_status)
            elif elapsed > timeout_seconds:
                hide_progress()
                self.root.after(0, lambda: messagebox.showerror(
                    "Timeout", 
                    f"Backend did not start within {timeout_seconds} seconds.\n"
                    "Check logs/startup_error.log for details."
                ))
                self.root.after(0, lambda: self.status_bar.config(text="Startup timeout"))
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            else:
                # Update progress
                progress_text = f"Starting... ({int(elapsed)}s)"
                self.root.after(0, lambda t=progress_text: self.status_bar.config(text=t))
                self.root.after(500, check_startup)

        self.root.after(1000, check_startup)

    def start_services(self):
        """Start both services in parallel."""
        self.start_button.config(state=tk.DISABLED)
        self.status_bar.config(text="Starting services...")

        # Route to frozen handler if running as EXE
        if self.is_frozen:
            self._start_services_frozen()
            return

        # Development mode: spawn external processes
        def worker():
            try:
                # Clean up zombies from previous run first
                self.cleanup_zombies()
                
                os.makedirs(os.path.join(self.base_dir, "data"), exist_ok=True)
                os.makedirs(os.path.join(self.base_dir, "logs"), exist_ok=True)
                backend_log_path = os.path.join(self.base_dir, "logs", "backend.log")
                frontend_log_path = os.path.join(self.base_dir, "logs", "frontend.log")
                
                # Check ports and handle conflicts
                # Backend
                if self.is_port_open(self.backend_port):
                    pids = self.find_pids_by_port(self.backend_port)
                    is_ours = False
                    for pid in pids:
                        if self.is_our_process(pid, 'backend'):
                            is_ours = True
                            self.kill_process(pid)
                    
                    if not is_ours and self.is_port_open(self.backend_port):
                        new_port = self.find_free_port(self.backend_port + 1)
                        self.root.after(0, lambda p=self.backend_port, n=new_port: messagebox.showinfo("Port Conflict", f"Backend port {p} is in use. Switching to {n}."))
                        self.backend_port = new_port
                        self.root.after(0, lambda: self.backend_port_label.config(text=f"Backend (:{self.backend_port}):"))

                # Frontend
                if self.is_port_open(self.frontend_port):
                    pids = self.find_pids_by_port(self.frontend_port)
                    is_ours = False
                    for pid in pids:
                        if self.is_our_process(pid, 'frontend'):
                            is_ours = True
                            self.kill_process(pid)
                    
                    if not is_ours and self.is_port_open(self.frontend_port):
                        new_port = self.find_free_port(self.frontend_port + 1)
                        self.root.after(0, lambda p=self.frontend_port, n=new_port: messagebox.showinfo("Port Conflict", f"Frontend port {p} is in use. Switching to {n}."))
                        self.frontend_port = new_port
                        self.root.after(0, lambda: self.frontend_port_label.config(text=f"Frontend (:{self.frontend_port}):"))

                # Open log files in append mode; keep handles so we can close them on shutdown
                self.backend_log_file = open(backend_log_path, "ab")
                self.frontend_log_file = open(frontend_log_path, "ab")

                # Prepare environment
                env = os.environ.copy()
                env['BACKEND_PORT'] = str(self.backend_port)
                env['FRONTEND_PORT'] = str(self.frontend_port)
                # Also set VITE vars for frontend
                env['VITE_BACKEND_PORT'] = str(self.backend_port)
                env['VITE_FRONTEND_PORT'] = str(self.frontend_port)

                # Start backend
                self.root.after(0, lambda: self.status_bar.config(text="Starting backend..."))
                self.backend_process = subprocess.Popen(
                    [get_python_exe(), "-m", "uvicorn", "src.api.main:app", 
                     "--host", self.backend_host, "--port", str(self.backend_port)],
                    cwd=self.base_dir,
                    env=env,
                    stdout=self.backend_log_file, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                # Wait for backend to become available before starting frontend
                backend_ready = False
                for _ in range(60):  # up to ~30s
                    if self.is_port_open(self.backend_port):
                        backend_ready = True
                        break
                    time.sleep(0.5)

                if not backend_ready:
                    raise RuntimeError("Backend did not start within 30 seconds. See logs/backend.log")

                # Backend is up; now start frontend
                self.root.after(0, lambda: self.status_bar.config(text="Starting frontend..."))

                node_modules = os.path.join(self.frontend_dir, "node_modules")
                if not os.path.exists(node_modules):
                    self.root.after(0, lambda: self.status_bar.config(text="Installing npm packages..."))
                    subprocess.run(
                        ["cmd", "/c", "npm", "install"],
                        cwd=self.frontend_dir,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )

                self.frontend_process = subprocess.Popen(
                    ["cmd", "/c", "npm", "run", "dev", "--", "--port", str(self.frontend_port)],
                    cwd=self.frontend_dir,
                    env=env,
                    stdout=self.frontend_log_file, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                # Wait briefly for both to start
                for _ in range(15):
                    if self.is_port_open(self.backend_port) and self.is_port_open(self.frontend_port):
                        break
                    time.sleep(0.5)

                # Validate that processes stayed up
                if self.backend_process and self.backend_process.poll() is not None:
                    raise RuntimeError(f"Backend failed to start. See log: {backend_log_path}")
                if self.frontend_process and self.frontend_process.poll() is not None:
                    raise RuntimeError(f"Frontend failed to start. See log: {frontend_log_path}")

                self.root.after(0, lambda: self.status_bar.config(text="Services started"))
                self.save_pids()
                # Re-check voice/STT dependencies after services start (in case user installed them)
                self.root.after(0, self.update_voice_status)

            except Exception as e:
                # Ensure any partially started processes are cleaned up
                if self.frontend_process:
                    self.kill_process(self.frontend_process.pid)
                    self.frontend_process = None
                if self.backend_process:
                    self.kill_process(self.backend_process.pid)
                    self.backend_process = None
                self.close_log_files()
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to start: {e}"))
                self.root.after(0, lambda: self.status_bar.config(text="Error"))
            finally:
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=False).start()

    def save_pids(self):
        """Save running PIDs to file."""
        pids = {}
        if self.backend_process:
            pids['backend'] = self.backend_process.pid
        if self.frontend_process:
            pids['frontend'] = self.frontend_process.pid
        
        pid_file = os.path.join(self.base_dir, "run.pid")
        try:
            import json
            with open(pid_file, 'w') as f:
                json.dump(pids, f)
        except:
            pass

    def cleanup_zombies(self):
        """Kill processes from previous run."""
        pid_file = os.path.join(self.base_dir, "run.pid")
        if not os.path.exists(pid_file):
            return
            
        try:
            import json
            with open(pid_file, 'r') as f:
                pids = json.load(f)
            
            if 'backend' in pids:
                pid = pids['backend']
                # Verify it's still our process type to avoid killing reused PIDs
                if self.is_our_process(pid, 'backend'):
                    self.kill_process(pid)
            
            if 'frontend' in pids:
                pid = pids['frontend']
                if self.is_our_process(pid, 'frontend'):
                    self.kill_process(pid)
                    
            try:
                os.remove(pid_file)
            except:
                pass
        except:
            pass

    def stop_services(self, wait=False):
        """Stop all services. If wait is True, block until shutdown finishes."""
        self.stop_button.config(state=tk.DISABLED)
        self.status_bar.config(text="Stopping services...")

        def worker():
            if self.is_frozen:
                self.server_should_exit = True
                self.status_bar.config(text="Stopping internal server...")
                
                # Gracefully shutdown uvicorn if we have a server reference
                if self.uvicorn_server:
                    try:
                        self.uvicorn_server.should_exit = True
                    except:
                        pass
                
                # Also kill any processes on our port (in case of hanging)
                pids = self.find_pids_by_port(self.backend_port)
                for pid in pids:
                    self.kill_process(pid)
                
                self.api_thread = None
                self.uvicorn_server = None
                
                time.sleep(0.5)
                self.root.after(0, lambda: self.status_bar.config(text="Stopped"))
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                try: 
                    self.close_log_files()
                except: pass
                return

            try:
                # Collect tracked PIDs
                frontend_pids = set()
                backend_pids = set()

                if self.frontend_process:
                    frontend_pids.add(self.frontend_process.pid)
                if self.backend_process:
                    backend_pids.add(self.backend_process.pid)

                # Also collect any processes bound to the known ports
                # Only kill if they are OUR processes (zombies)
                for pid in self.find_pids_by_port(self.frontend_port):
                    if self.is_our_process(pid, 'frontend'):
                        frontend_pids.add(pid)
                
                for pid in self.find_pids_by_port(self.backend_port):
                    if self.is_our_process(pid, 'backend'):
                        backend_pids.add(pid)

                for pid in frontend_pids:
                    self.kill_process(pid)
                for pid in backend_pids:
                    self.kill_process(pid)

                self.frontend_process = None
                self.backend_process = None
                self.close_log_files()
                
                try:
                    os.remove(os.path.join(self.base_dir, "run.pid"))
                except:
                    pass

                time.sleep(0.5)
                if self.root.winfo_exists():
                    self.root.after(0, lambda: self.status_bar.config(text="Services stopped"))
            finally:
                if self.root.winfo_exists():
                    self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

        thread = threading.Thread(target=worker, daemon=False)
        thread.start()
        if wait:
            thread.join(timeout=5)

    def force_stop_ports(self):
        """Force stop ALL processes on configured backend and frontend ports."""
        self.force_stop_button.config(state=tk.DISABLED)
        self.status_bar.config(text="Force stopping ports...")

        def worker():
            killed_count = 0
            try:
                # Kill ALL processes on backend port
                backend_pids = self.find_pids_by_port(self.backend_port)
                for pid in backend_pids:
                    self.kill_process(pid)
                    killed_count += 1

                # Kill ALL processes on frontend port
                frontend_pids = self.find_pids_by_port(self.frontend_port)
                for pid in frontend_pids:
                    self.kill_process(pid)
                    killed_count += 1

                # Clear our tracked processes too
                self.backend_process = None
                self.frontend_process = None
                self.api_thread = None
                self.uvicorn_server = None
                self.close_log_files()

                # Remove PID file
                try:
                    os.remove(os.path.join(self.base_dir, "run.pid"))
                except:
                    pass

                time.sleep(0.5)
                if self.root.winfo_exists():
                    if killed_count > 0:
                        msg = f"Force stopped {killed_count} process(es)"
                    else:
                        msg = "No processes found on ports"
                    self.root.after(0, lambda: self.status_bar.config(text=msg))
            except Exception as e:
                if self.root.winfo_exists():
                    self.root.after(0, lambda: self.status_bar.config(text=f"Error: {e}"))
            finally:
                if self.root.winfo_exists():
                    self.root.after(0, lambda: self.force_stop_button.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=False).start()

    def kill_process(self, pid):
        """Kill process tree."""
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except:
            pass

    def close_log_files(self):
        """Close any open log file handles."""
        for attr in ("backend_log_file", "frontend_log_file"):
            fh = getattr(self, attr, None)
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
                setattr(self, attr, None)

    def get_process_command_line(self, pid):
        """Get the command line arguments for a process ID."""
        try:
            # Use wmic to get command line
            cmd = ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout.strip()
            # Output usually looks like:
            # CommandLine
            # "C:\path\to\python.exe" script.py args
            # So we join all lines after the header
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if len(lines) > 1:
                return " ".join(lines[1:])
            return ""
        except Exception:
            return ""

    def is_our_process(self, pid, service_type):
        """
        Check if a process belongs to us based on its command line.
        service_type: 'backend' or 'frontend'
        """
        cmdline = self.get_process_command_line(pid).lower()
        if not cmdline:
            return False
            
        if service_type == 'backend':
            # Check for uvicorn and our app module
            return 'uvicorn' in cmdline and 'src.api.main:app' in cmdline
        elif service_type == 'frontend':
            # Check for vite or npm run dev
            return 'vite' in cmdline or ('npm' in cmdline and 'run' in cmdline)
        return False

    def find_pids_by_port(self, port):
        """Find PIDs listening on the given port."""
        pids = set()
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                local = parts[1]
                if re.search(rf":{port}$", local):
                    try:
                        pids.add(int(parts[-1]))
                    except ValueError:
                        continue
        except Exception:
            pass
        return pids

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)
    
    def open_logs_folder(self):
        logs_dir = os.path.join(self.base_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        os.startfile(logs_dir)
        
    def on_closing(self):
        services_running = (
            self.backend_process or
            self.frontend_process or
            self.api_thread or
            self.is_port_open(self.backend_port) or
            self.is_port_open(self.frontend_port)
        )
        if services_running:
            if messagebox.askokcancel("Quit", "Stop services and quit?"):
                self.stop_services(wait=True)
                self.root.destroy()
        else:
            self.root.destroy()


if __name__ == "__main__":
    # Single Instance Check
    mutex_name = "Local\\AAC_Assistant_Instance_Lock"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, True, mutex_name)
    last_error = kernel32.GetLastError()
    
    if last_error == 183: # ERROR_ALREADY_EXISTS
        # CRITICAL: Close splash screen immediately so it doesn't block the message box
        if pyi_splash:
            pyi_splash.close()

        # App is seemingly already running. Check for zombie processes.
        is_frozen = getattr(sys, 'frozen', False)
        found_zombies = False
        
        if is_frozen:
            try:
                exe_name = os.path.basename(sys.executable)
                current_pid = os.getpid()
                
                # Use tasklist to find other instances - using partial match to be safe
                # Filter by AAC_Assistant* matches both .exe and potentially truncated names
                cmd = 'tasklist /FI "IMAGENAME eq AAC_Assistant*" /FO CSV /NH'
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000) # CREATE_NO_WINDOW
                
                zombies = []
                for line in result.stdout.splitlines():
                    if not line.strip(): continue
                    # CSV format: "Image Name","PID","Session Name","Session#","Mem Usage"
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            pid_str = parts[1].strip('"')
                            pid = int(pid_str)
                            if pid != current_pid:
                                zombies.append(pid)
                        except ValueError:
                            pass
                            
                if zombies:
                    found_zombies = True
                    msg = (f"Another instance is running (PID: {', '.join(map(str, zombies))}).\n\n"
                           "This looks like a 'zombie' process from a previous run.\n"
                           "Do you want to force close it?")
                    
                    # MB_YESNO=0x4, MB_ICONWARNING=0x30, MB_TOPMOST=0x40000
                    # Using TOPMOST to ensure it's visible even if splash didn't close properly
                    response = ctypes.windll.user32.MessageBoxW(0, msg, "AAC Assistant - Conflict", 0x4 | 0x30 | 0x40000)
                    
                    if response == 6: # IDYES
                        killed_count = 0
                        for pid in zombies:
                            subprocess.run(f"taskkill /F /PID {pid}", capture_output=True, creationflags=0x08000000)
                            killed_count += 1
                        
                        ctypes.windll.user32.MessageBoxW(0, 
                            f"Terminated {killed_count} process(es).\nPlease restart the application.", 
                            "AAC Assistant", 0x40 | 0x40000) # MB_ICONINFORMATION | MB_TOPMOST
                        sys.exit(0)
                        
            except Exception as e:
                # Fallback if detection fails
                pass

        if not found_zombies:
            ctypes.windll.user32.MessageBoxW(0, "AAC Assistant is already running.", "AAC Assistant", 0x40 | 0x1 | 0x40000)
        
        sys.exit(0)

    root = tk.Tk()
    app = AACLauncher(root)
    
    # Close splash screen once the GUI is ready to be shown
    if pyi_splash:
        pyi_splash.close()
        
    root.mainloop()
    
    # Force exit to ensure no lingering threads keep the process alive
    sys.exit(0)
