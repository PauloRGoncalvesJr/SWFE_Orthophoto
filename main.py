from pathlib import Path

from app.gui import SidewalkAnnotationApp


def main() -> None:
	app = SidewalkAnnotationApp(project_root=Path(__file__).resolve().parent)
	app.run()


if __name__ == "__main__":
	main()
