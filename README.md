# BeoLink Bridge for Home Assistant

## Requirements
- BeoLink app installed on your iOS device

## Installation
Files are installed by downloading the files to your custom_components folder directly from here or by adding it via HACS.

Afterwards you can go to the Integrations sections and click the add integration button. Search for BeoLink and choose the newly added BeoLink integration.

You will be asked to name your BeoLink Bridge. This is the name you will see in the app.

It will automatically lookup all supported entities and expose them to BeoLink app use. ZereConf might not be working yet, so you will need to add the BeoLink Bridge to the app manually, by entering the IP of your Home Assistant installation in the App under Settings -> "+"

## Changelog
- 2023-07-23 Initial Version

## Known limitations
- B&O and other audio devices not yet supported
- Display of surveilance cameras on B&O TVs not yet implemented
- RTSP streaming of cameras not implemented. MJPEG is working as fallback solution
- Thermostats are under implementation
- Scenes are under implementation
- Lights: Set color not working/supported
- Security not yet implemented