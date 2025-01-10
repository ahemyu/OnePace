from pathlib import Path
import sys
import subprocess
from typing import List, Optional
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
        self.video_dir = Path("/home/emre-fox/Videos/Dressrosa")
        self.current_episode = self.load_progress()
        self.videos = self.get_sorted_videos()
        
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
    
    def play_current(self) -> None:
        """Play the current episode using MPV, handling missing episodes."""
        if not self.videos:
            QMessageBox.information(self, "Error", "No video files found!")
            return
            
        # Find the index of the current episode in our available videos
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
            self.current_process.terminate()
            self.current_process = None
        
        current_video = self.videos[current_idx]
        
        # Start MPV with specific options
        self.current_process = subprocess.Popen([
            'mpv',
            '--hwdec=auto',
            '--profile=gpu-hq',
            '--force-window=yes',
            str(current_video)
        ])
        
        self.check_timer.start()
    
    def check_video_end(self) -> None:
        """Check if video has ended and prompt for next action."""
        if self.current_process and self.current_process.poll() is not None:
            self.check_timer.stop()
            reply = QMessageBox.question(
                self,
                'Video Finished',
                'Would you like to proceed to the next episode?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.next_episode()
    
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
            try:
                # First try to terminate gracefully
                self.current_process.terminate()
                # Wait for up to 3 seconds for the process to end
                self.current_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # If it doesn't terminate within 3 seconds, kill it forcefully
                self.current_process.kill()
            except Exception as e:
                print(f"Error while closing MPV: {e}")
                
        # Force Python to exit
        sys.exit(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoPlayer()
    window.show()
    sys.exit(app.exec())