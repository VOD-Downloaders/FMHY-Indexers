# FMHY Indexers

A central collection of all supported [freemediaheckyeah](https://fmhy.net/video) sites and their respective instructions for [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader).

## How this works

This repository contains indexer specifications for multiple [freemediaheckyeah](https://fmhy.net/video) sites and is expanding with each release.  
The indexer specification files are under the `vX.X` folder corresponding with that version of [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader). This way of saving specifications allows for better backwards compatibility.

Latest indexers: [`v0.3`](./v0.3)

## How to create an indexer

An indexer is a single JSON file describing one site and how [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader) should download from it. Add a new indexer by creating `<sitename>.json` inside the latest `vX.X` folder.

### Steps

1. Copy an existing indexer (e.g. [`v0.3/videasy.json`](./v0.3/videasy.json)) as a starting point.
2. Name the file after the site in lowercase (e.g. `vidking.json`).
3. Fill in the fields below.
4. Verify the indexer works with [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader).

### Specification

```jsonc
{
    // Display name of the site.
    "name": "Videasy",

    // Different server names of the backend. All use the same decryption logic
    "server_list": [
		{
		    // Name of a server 
			"name": "Neon",
			// Description of the server
			"description": "Best server for both movies and series.",
			// The url to send the requests to 
			"search_url": "https://api.videasy.to/mb-flix/sources-with-title",
			// Extra headers to send with the request specific to this server
			"headers": null,
		}
		
    ],
	
    // Whether the site is protected by Cloudflare. Affects how requests are made.
    "uses_cloudflare": false,

    // Search settings
    "search": {
	    // The URL the browser will pretend the requests are coming from
		"emulate_url": "https://player.videasy.to/",
		// Extra headers to send with the requests
		"headers": {
			"Referer": "https://player.videasy.to/"
		}
	},
	
	// Stream retrieval settings
	"stream": {
	    // Steam video type that is returned ("index" or "mp4")
		"type": "index",
		// Extra headers to send with the stream reading requests
		"headers": {
			"Referer": "https://player.videasy.to/"
		}
	},

    // Download settings
    "download": {
        // Settings applied while fetching each segment.
        "segment_download": {
            // Seconds to wait for a segment before giving up.
            "segment_timeout": 5,
            // Number of times to retry a failed segment.
            "segment_attempts": 5,
            // Extra HTTP headers sent with each segment request.
            "headers": {
                "Referer": "https://example.com"
            }
        },

        // Byte trimming applied to each segment after it is downloaded.
        // Use this to strip junk/obfuscation bytes some sites prepend or append.
        "segment_post_download": {
            "remove_front_bytes": 0,
            "remove_back_bytes": 0
        }
    }
}
```

> The spec is versioned: files under `v0.3` follow the `v0.3` standard. When the format changes, a new `vX.X` folder is created so older downloader versions keep working. Edit indexers in the latest version folder only.

## Contributing

Contributions are highly appreciated.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes
4. Ensure everything works with [FMHY-Downloader](https://github.com/VOD-Downloaders/FMHY-Downloader).
5. Open a pull request with a clear description of what you changed and why

## License

This project is licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE.txt) for the full license text.
