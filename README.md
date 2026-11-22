# ClipCraft
<img width="1172" height="324" alt="Logo Aplikasi ClipCraft Berkilau" src="https://github.com/user-attachments/assets/6256fe87-6b50-49d2-9314-82b9e02e4eed" />


A Python-based video downloader powered by yt-dlp, supporting YouTube and various other media platforms


## "Download Any Video"

🚀 Getting Started

  **Clone repository**
  ```
  git clone https://github.com/USERNAME/ClipCraft.git
  
  cd ClipCraft
  ```

📦 Installation
 
  Linux :
  
  **Create virtual environment**

  ```
  python3 -m venv .venv
  ```

  **Activate virtual environment**
 

  ```
  source .venv/bin/activate
  ```

⚙️ Configuration

  **Add standard needed package**
  ```
    pip install -U "yt-dlp[default]"
    pip install git+https://github.com/tribixbite/yt-dlp-threads
    pip install pyside6
  ```

  **Or complete dependencies**
  
  ```pip install -r requirements.txt```

  **Add PO (Proof of Origin) Token Providers Server***
  
  Create & run at once if you don't have one (first install)

  ```
  docker run --name bgutil-provider -d --init \\n  -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
  ```
  Or run it if you have one
  ```
  docker start bgutil-provider 
  ```

  Set DNS to get a rid blocking, me using Cloudflare
  ```
  sudo resolvectl dns enp3s0 1.1.1.1 1.0.0.1
  sudo resolvectl flush-caches

  sudo resolvectl dns wlo1 1.1.1.1 1.0.0.1
  sudo resolvectl flush-caches
  ```
  Check whether the website is reachable  
  ```
  python -c "import requests; r=requests.get('https://situs_nakal_anda.com', timeout=15); print(r.status_code, r.url)"
  ```

## Threads Support (threads.com)

ClipCraft includes a custom yt-dlp extractor plugin
for downloading publicly accessible videos from Threads.

Supported features:
- Standard Threads video posts.
- Quoted video attachments.
- Progressive MP4 formats.
- DASH video streams.
- Video metadata and thumbnails.

### Plugin Structure

The custom extractor is maintained inside the repository:

```
yt_dlp_plugins/
└── extractor/
    └── threads.py
```

The plugin is loaded by yt-dlp through its plugin discovery mechanism. I put patch for threads.com video download error here, please don't forget to replace the real threads.py in your venv directory in my case I use .venv: 

```
cp yt_dlp_plugins/extractor/threads.py /your_venv_directory/.venv/lib/python3.12/site-packages/yt_dlp_plugins/extractor/threads.py
```

### Limitations

- Only publicly accessible Threads posts are supported.
- Private or login-restricted posts may not be downloadable.
- Threads may change its internal API or embedded page structure,
  which can affect extractor compatibility.


📸 Screenshot

## Video Downloader

### GUI

<img width="960" height="540" alt="ClipCraft_012" src="https://github.com/user-attachments/assets/b7aa195a-0180-4e68-b408-8effefb3797e" />

For YouTube video **ClipCart** has special ability by downloading "The Most Played Segment", user just check the checkbox under the "Folder Keluaran" then the application automaticaly check if available or not.

If user use this range segment then ClipCart will set to download only this segment.

### CLI

Video Downloader - CLI.py
 

<img width="960" height="540" alt="Selection_1330" src="https://github.com/user-attachments/assets/72d079de-9bc3-44d4-83d8-ae887905be1a" />
 

## Video Compressor

<img width="960" height="540" alt="ClipCraft_013" src="https://github.com/user-attachments/assets/6f3f3abf-e157-4c99-a010-fef6b09bdfbb" />

## Video Cutter

<img width="960" height="540" alt="ClipCraft_020" src="https://github.com/user-attachments/assets/7ea11223-853d-4736-8f52-a25270f55a66" />


## Add Text / Subtitle

<img width="577" height="536" alt="Selection_1406" src="https://github.com/user-attachments/assets/b3ec289f-6dbe-4599-8795-a9ba452f28df" />


**Just another vibe-coded project.** 😎


This application allows you to download videos from various popular websites. It is what it is — no fancy UI, no complicated setup. Just run it, paste your link, and start downloading.

## Legal

📄 License

This project is licensed under the MIT License.

SABR Downloader uses third-party software, including yt-dlp, which is distributed under its own respective license.

Please refer to the respective projects for their licensing terms.
SABR Downloader uses third-party software,including yt-dlp, which is distributed under its own respective license.

See the respective projects for their licensing terms.


📄 Term of Service

Users of this application must comply with the [Term of Service](TERMS.md)



**Happy downloading!**


