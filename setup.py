from setuptools import setup, find_packages

setup(
    name="sodo",
    version="0.1.0",
    description="YouTube → MP3 downloader CLI",
    author="asim",
    packages=find_packages(),
    install_requires=[
        "yt-dlp>=2024.1.0",
        "click>=8.1",
    ],
    entry_points={
        "console_scripts": [
            "sodo = sodo.cli:main",
        ],
    },
)
