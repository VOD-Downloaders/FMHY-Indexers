# FMHY Indexers

A central collection of all supported [freemediaheckyeah](https://fmhy.net/video) sites and their respective instructions for [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader).

## How this works

This repository contains indexer specifications for multiple [freemediaheckyeah](https://fmhy.net/video) sites and is expanding with each release.  
The indexer specification files are under the `vX.X` folder corresponding with that version of [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader). This way of saving specifications allows for better backwards compatibility.

Latest indexers: [`v0.1`](./v0.1)

## How to create an indexer

An indexer is a single JSON file describing one site and how [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader) should download from it. Add a new indexer by creating `<sitename>.json` inside the latest `vX.X` folder.

### Steps

1. Copy an existing indexer (e.g. [`v0.1/cineby.json`](./v0.1/cineby.json)) as a starting point.
2. Name the file after the site in lowercase (e.g. `aether.json`).
3. Fill in the fields below.
4. Verify the indexer works with [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader).

### Specification

```jsonc
{
    // Display name of the site.
    "name": "Cineby",

    // Primary site URL. Used to resolve the {base_url} placeholder.
    "url": "https://www.cineby.at/",

    // Alternative URLs that serve the same content. May be empty.
    "mirrors": ["https://www.cineplay.to/", "https://www.fmovies.nz/"],

    // Whether the site is protected by Cloudflare. Affects how requests are made.
    "uses_cloudflare": false,

    "download": {
        // Settings applied while fetching each segment.
        "segment_pre_download": {
            // Seconds to wait for a segment before giving up.
            "segment_timeout": 5,
            // Number of times to retry a failed segment.
            "segment_attempts": 5,
            // Extra HTTP headers sent with each segment request.
            // {base_url} is replaced with the value of "url".
            // {segment_url} is replaced with full url of the segment.
            "headers": {
                "Referer": "{base_url}"
            }
        },

        // Byte trimming applied to each segment after it is downloaded.
        // Use this to strip junk/obfuscation bytes some sites prepend or append.
        "segment_post_download": {
            "remove_front_bytes": 0,
            "remove_back_bytes": 0
        },

        // How the playlist is resolved.
        "method": {
            // "master" — start from a master HLS playlist and pick a stream.
            // "index"  — the URL points directly at the media/index playlist.
            "type": "index",
            // Seconds to wait before fetching the playlist.
            "wait_time": 6,
            // Number of times to retry resolving the playlist.
            "retries": 5
        }
    }
}
```

> The spec is versioned: files under `v0.1` follow the `v0.1` standard. When the format changes, a new `vX.X` folder is created so older downloader versions keep working. Edit indexers in the latest version folder only.

## Contributing

Contributions are highly appreciated.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes
4. Ensure everything works with [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader).
5. Open a pull request with a clear description of what you changed and why

## License

This project is licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE.txt) for the full license text.
