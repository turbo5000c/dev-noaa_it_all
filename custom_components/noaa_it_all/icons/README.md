# NOAA Integration Icon

This directory contains custom icon assets for the NOAA Integration.

## Icon Design

The custom icons combine Home Assistant's house iconography with NOAA's space weather monitoring themes:

### Design Elements
- **Home Assistant House**: Central house structure representing the Home Assistant platform (bold design)
- **Solar Activity**: Enhanced sun rays and solar gradient representing NOAA's solar monitoring
- **Magnetic Field Lines**: Bold curved blue lines representing geomagnetic field monitoring
- **Space Weather Elements**: Bright stars and aurora-like effects representing space weather data
- **NOAA-HASS Branding**: Bold blue and white color scheme with "NOAA-HASS" text to represent the integration name

### Files
- `icon.svg` - Full-size icon (200x200) with detailed elements
- `icon-small.svg` - Simplified icon (48x48) optimized for small display sizes

## Current Implementation

The integration currently uses the Material Design Icon `mdi:satellite-variant` in the manifest.json, which is appropriate for space weather monitoring functionality.

## Custom Icon Usage

If you want to use the custom SVG icons instead of the MDI icon:

1. The SVG files are provided for reference and future use
2. Home Assistant integrations typically use MDI icons for best compatibility
3. Custom icons may require additional integration work to display properly in all contexts

## Icon Rationale

The `mdi:satellite-variant` icon was chosen because this integration:
- Monitors space weather from NOAA satellites
- Provides real-time geomagnetic and solar activity data
- Displays satellite-derived images (geoelectric field, aurora forecasts)
- Represents NOAA's space weather prediction center functionality

The icon effectively communicates that this integration deals with satellite-based space weather monitoring.