from setuptools import setup, find_packages

setup(
    name="sodo",
    version="0.1.0",
    description="YouTube → MP3 downloader CLI",
    author="asim",
    packages=find_packages(include=["sodo", "sodo.*"]),
    install_requires=[
        "click>=8.0",
        "yt-dlp>=2024.1.0",
    ],
    entry_points={
        "console_scripts": [
            "sodo = sodo.cli:main",
        ],
    },
    zip_safe=False,
)
