# BeoLink Bridge for Home Assistant

## Requirements
- BeoLink app installed on your iOS device

## Installation
Files are installed by downloading the files to your custom_components folder directly from here or by adding it via HACS.

Afterwards you can go to the Integrations sections and click the add integration button. Search for BeoLink and choose the newly added BeoLink integration.

You will be asked to name your BeoLink Bridge. This is the name you will see in the app.

It will automatically lookup all supported entities and expose them to BeoLink app use. An entity or device must be added to an Area in order to show up in the Beoliving app. ZereConf might not be working yet, so you will need to add the BeoLink Bridge to the app manually, by entering the IP of your Home Assistant installation in the App under Settings -> "+"

## Changelog
- 2023-07-23 Initial Version
- 2023-10-14 Major Release adding support for BeoPlay devices via the BeoPlay components. Added support for native HA Thermostats & Alarm
- 2023-12-03 Added support for TrustedNetworksAuthProvider

## Known limitations
- Only BeoPlay devices are supported via the BeoPlay component https://github.com/giachello/beoplay
- Display of surveilance cameras on B&O TVs not yet implemented
- RTSP streaming of cameras not implemented. MJPEG is working as fallback solution
- Scenes are under implementation