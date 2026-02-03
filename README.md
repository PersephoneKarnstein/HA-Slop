# Home Assistant Custom Integrations

A collection of custom [Home Assistant](https://www.home-assistant.io/) integrations, each installable independently. They were vibe coded so I disown them, do whatever you want with them.

## Integrations

### [Bluesky Feed](bluesky/)

![bluesky](bsky-feed.png)

Displays a Bluesky social media feed as a Lovelace dashboard card. Supports the authenticated user's timeline, a specific author's posts, or a custom feed URI. Features interactive like/repost buttons, rich text rendering, images, quoted posts, and external link previews. Distributed via HACS.

See [bluesky/README.md](bluesky/README.md) for setup and configuration.

### [Citizen Incidents](citizen-integration/)

![citizen](citizen.png)

Shows live incident reports from Citizen.com as color-coded geo_location entities on the Home Assistant map. Incidents are colored by recency — from purple (just reported) through red, orange, and yellow down to gray (oldest). Includes a standalone GeoJSON server as an alternative deployment option.

See [citizen-integration/README.md](citizen-integration/README.md) for setup and configuration.

### [Seedtime Garden Planner](seedtime-integration/)

![seedtime](seedtime.png)

Renders an interactive SVG garden plan from [Seedtime.us](https://seedtime.us) with a timeline slider for scrubbing through planting dates, crop tooltips on hover/tap, and a calendar entity for seeding and harvest milestones.

See [seedtime-integration/README.md](seedtime-integration/README.md) for setup and configuration.

## Installation

Each integration is self-contained in its directory. Install by copying the relevant `custom_components/<domain>/` folder into your Home Assistant config directory and restarting Home Assistant. See individual READMEs for detailed instructions.
