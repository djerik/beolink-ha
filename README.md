# BeoLink Bridge for Home Assistant

## Requirements
- Port 80 available or knowledge of how to create proxy setup
- BeoLink app installed on your iOS device

## Installation
Files are installed by downloading the files to your custom_components folder directly from here or by adding it via HACS.

Afterwards you must go to the Integrations sections and click the add integration button. Search for BeoLink and choose the newly added BeoLink integration.

You will be asked to name your BeoLink Bridge. This is the name you will see in the app.

Next you must go the settings of BeoLink and configure what entities to show in the BeoLink app. An entity or device must be added to an Area in order to show up in the Beoliving app. ZereConf might not be working in your network configuration, in which case you will need to add the BeoLink Bridge to the app manually, by entering the IP of your Home Assistant installation in the App under Settings -> "+"

You login using your Home Assistant user name and password. If you are using Trusted Network, any user name and password can be entered.

## Changelog
- 2023-07-23 Initial Version
- 2023-10-14 Major Release adding support for BeoPlay devices via the BeoPlay components. Added support for native HA Thermostats & Alarm
- 2023-12-03 Added support for TrustedNetworksAuthProvider
- 2023-12-23 Improved handling of None object references
- 2024-01-25 Major overhaul of code
- 2024-01-26 Fixed import path blocking config flow
- 2024-02-22 Fixed bugs in thermostat handling and added support for BeoLink 2 app

## Known limitations
- Only BeoPlay devices are supported via the BeoPlay component https://github.com/giachello/beoplay
- Display of surveilance cameras on B&O TVs not yet implemented
- RTSP streaming of cameras not implemented. MJPEG is working as fallback solution
- Scenes are under implementation
- Entities cannot have ? or / in the name
- Entities with same name can cause problems

![image](https://github.com/djerik/beolink-ha/assets/1743422/cea1269c-f24a-42bf-823b-cba93f7d0b2f)

![image](https://github.com/djerik/beolink-ha/assets/1743422/0b40b828-f0d5-42a4-a7a5-39ff95d0a225)

![image](https://github.com/djerik/beolink-ha/assets/1743422/6f994a71-eda6-4d5e-bd51-6ecbc01e43cc)

![image](https://github.com/djerik/beolink-ha/assets/1743422/55a8fda9-6b3b-464d-a456-fb5d8cfde36c)

![image](https://github.com/djerik/beolink-ha/assets/1743422/edd30a1b-3ac5-4661-be4b-75d5dbfc8001)

![image](https://github.com/djerik/beolink-ha/assets/1743422/deee992a-9507-4eee-823a-e369c6e3b022)

![image](https://github.com/djerik/beolink-ha/assets/1743422/90dc92ef-27d0-4cf4-baf3-4c257311f1b4)
