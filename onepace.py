from pathlib import Path
import sys
import subprocess
import json
from typing import List, Optional, Dict
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QPushButton, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer

class VideoPlayer(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MPV Video Player")
        self.setGeometry(100, 100, 400, 200)
        
        # Initialize video tracking
        self.video_dir = Path("/home/emre-fox/Videos/episodes/Wano")
        self.current_episode = self.load_progress()
        self.videos = self.get_sorted_videos()
        
        # Position tracking
        self.positions: Dict[str, float] = self.load_positions()
        self.last_position: float = 0
        
        # MPV process tracking
        self.current_process: Optional[subprocess.Popen] = None
        self.check_timer = QTimer()
        self.check_timer.setInterval(1000)  # Check every second
        self.check_timer.timeout.connect(self.check_video_end)
        
        # Set up the UI
        self.init_ui()
        
    def init_ui(self) -> None:
        """Set up the user interface elements."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Current episode label
        self.episode_label = QLabel(f"Current Episode: {self.current_episode}")
        layout.addWidget(self.episode_label)
        
        # Play button
        play_button = QPushButton("Play Current Episode")
        play_button.clicked.connect(self.play_current)
        layout.addWidget(play_button)
        
        # Delete previous button
        delete_button = QPushButton("Delete Previous Episode")
        delete_button.clicked.connect(self.delete_previous)
        layout.addWidget(delete_button)
        
        # Next episode button
        next_button = QPushButton("Mark as Watched && Next")
        next_button.clicked.connect(self.next_episode)
        layout.addWidget(next_button)
    
    def get_sorted_videos(self) -> List[Path]:
        """Get all .mkv files sorted by number, handle missing episodes."""
        # First get all mkv files
        videos = list(self.video_dir.glob("*.mkv"))
        
        # Sort them by their numeric names
        videos.sort(key=lambda x: int(x.stem))
        
        if not videos:
            return []
            
        # Check if we need to adjust current_episode based on the first available episode
        first_episode = int(videos[0].stem)
        if first_episode > self.current_episode:
            self.current_episode = first_episode
            self.save_progress()
        
        return videos
    
    def load_progress(self) -> int:
        """Load the current episode from progress file."""
        progress_file = Path(".progress")
        if progress_file.exists():
            return int(progress_file.read_text())
        return 1
    
    def save_progress(self) -> None:
        """Save current episode to progress file."""
        Path(".progress").write_text(str(self.current_episode))

    def load_positions(self) -> Dict[str, float]:
        """Load saved video positions from JSON file."""
        position_file = Path(".positions.json")
        if position_file.exists():
            return json.loads(position_file.read_text())
        return {}

    def save_positions(self) -> None:
        """Save video positions to JSON file."""
        Path(".positions.json").write_text(json.dumps(self.positions))

    def get_video_position(self) -> None:
        """Get current video position using MPV's IPC socket."""
        if self.current_process:
            try:
                # Use echo '{ "command": ["get_property", "time-pos"] }' | socat - /tmp/mpvsocket
                result = subprocess.run(
                    ['socat', '-', '/tmp/mpvsocket'],
                    input='{ "command": ["get_property", "time-pos"] }\n',
                    text=True,
                    capture_output=True
                )
                if result.stdout:
                    response = json.loads(result.stdout)
                    if 'data' in response:
                        self.last_position = float(response['data'])
            except Exception as e:
                print(f"Error getting position: {e}")

    def get_video_duration(self, video_path: Path) -> Optional[float]:
        """Get video duration using ffprobe."""
        try:
            result = subprocess.run([
                'ffprobe', 
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ], capture_output=True, text=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"Error getting duration: {e}")
            return None
    
    def play_current(self) -> None:
        """Play the current episode using MPV, resuming from last position."""
        if not self.videos:
            QMessageBox.information(self, "Error", "No video files found!")
            return
            
        # Find the current episode video
        current_idx = -1
        for idx, video in enumerate(self.videos):
            if int(video.stem) == self.current_episode:
                current_idx = idx
                break
        
        if current_idx == -1:
            QMessageBox.information(
                self, 
                "Error", 
                f"Episode {self.current_episode} not found!"
            )
            return
            
        # Stop any existing playback
        if self.current_process:
            self.get_video_position()  # Save current position before stopping
            self.current_process.terminate()
            self.current_process = None
        
        current_video = self.videos[current_idx]
        video_key = str(current_video)
        start_position = self.positions.get(video_key, 0)
        
        # Start MPV with position and IPC socket
        self.current_process = subprocess.Popen([
            'mpv',
            '--hwdec=auto',
            '--profile=gpu-hq',
            '--force-window=yes',
            f'--start={start_position}',
            '--input-ipc-server=/tmp/mpvsocket',  # Enable IPC socket for position tracking
            str(current_video)
        ])
        
        self.check_timer.start()
    
    def check_video_end(self) -> None:
        """Check if video has ended and save position."""
        if self.current_process:
            if self.current_process.poll() is not None:
                self.check_timer.stop()
                current_video = next(
                    (v for v in self.videos if int(v.stem) == self.current_episode), 
                    None
                )
                
                if current_video:
                    video_key = str(current_video)
                    # Only prompt for next episode if we're near the end
                    video_duration = self.get_video_duration(current_video)
                    if video_duration and self.last_position >= (video_duration - 30):
                        # We're at the end of the video
                        self.positions.pop(video_key, None)  # Remove position for completed episode
                        self.save_positions()
                        
                        reply = QMessageBox.question(
                            self,
                            'Video Finished',
                            'Would you like to proceed to the next episode?',
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            self.next_episode()
                    else:
                        # Save the last position
                        self.positions[video_key] = self.last_position
                        self.save_positions()
            else:
                # Update position while video is playing
                self.get_video_position()
    
    def delete_previous(self) -> None:
        """Delete the previous episode after confirmation."""
        if self.current_episode <= 1:
            QMessageBox.information(self, "Info", "No previous episode to delete.")
            return
        
        # Find the previous episode in our available videos
        prev_episodes = [v for v in self.videos if int(v.stem) < self.current_episode]
        if not prev_episodes:
            QMessageBox.information(self, "Info", "No previous episode found to delete.")
            return
            
        prev_video = max(prev_episodes, key=lambda x: int(x.stem))
        reply = QMessageBox.question(
            self,
            'Confirm Deletion',
            f'Delete {prev_video.name}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove position data for deleted episode
            self.positions.pop(str(prev_video), None)
            self.save_positions()
            
            prev_video.unlink()
            self.videos = self.get_sorted_videos()  # Refresh video list
            QMessageBox.information(self, "Success", "Previous episode deleted.")
    
    def next_episode(self) -> None:
        """Move to next episode and save progress."""
        if not self.videos:
            QMessageBox.information(self, "Error", "No video files found!")
            return
            
        # Find the next available episode number
        current_video_numbers = [int(v.stem) for v in self.videos]
        next_episodes = [n for n in current_video_numbers if n > self.current_episode]
        
        if not next_episodes:
            QMessageBox.information(self, "Complete", "You've reached the last episode!")
            return
            
        self.current_episode = min(next_episodes)  # Get the next available episode
        self.episode_label.setText(f"Current Episode: {self.current_episode}")
        self.save_progress()
        self.play_current()
    
    def closeEvent(self, event) -> None:
        """Clean up when closing the application."""
        if self.current_process:
            self.get_video_position()  # Save final position
            current_video = next(
                (v for v in self.videos if int(v.stem) == self.current_episode), 
                None
            )
            if current_video:
                self.positions[str(current_video)] = self.last_position
                self.save_positions()
                
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
            except Exception as e:
                print(f"Error while closing MPV: {e}")
                
        sys.exit(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoPlayer()
    window.show()
    sys.exit(app.exec())