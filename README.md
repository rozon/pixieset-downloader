# pixieset-downloader
Python tool that automates the process of downloading images from a Pixieset collection using Selenium.

## Overview
Pixieset is a platform commonly used by photographers to share and sell their photos. This script simplifies the retrieval of images from a given Pixieset collection, allowing for the efficient downloading of multiple images at once.

## Requirements
- Python 3.11+
- pipenv
- Firefox

## Installation
1. Clone this repository.
2. Install required Python libraries: `pipenv install`

## Usage
1. Activate virtual environment: `pipenv shell`
2. Rename `.env.example` to `.env` and add the proper values for each key.
3. Run the script: `pipenv run download`

## Environment Variables
- `PIXIESET_COLLECTION_URL`: Replace this with the URL of the Pixieset collection you want to scrape. For example:
```text
PIXIESET_COLLECTION_URL=https://josevilla.pixieset.com/lilyandjonathan/
```
- `DOWNLOAD_DIRECTORY`: Set this to the local directory where you want the images to be downloaded.

## Limitations
The downloaded images might still retain watermarks and potentially be of lower quality compared to the originals – which is good to support your local photographers! It is also not guaranteed that absolutely all images have been downloaded, so this should be verified manually.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License
This project is licensed under the [MIT License](LICENSE).