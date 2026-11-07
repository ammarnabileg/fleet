The admin panel's map (assets/js/app/map.js). Served from our servers; nothing here calls a third party.

maplibre/               MapLibre GL JS 6.12.0 (ES modules)          BSD-3-Clause    maplibre/LICENSE.txt
pmtiles.js              pmtiles 4.5.0 (Protomaps)                   BSD-3-Clause    github.com/protomaps/PMTiles
basemaps.js             @protomaps/basemaps 5.7.2 (map style)       BSD-3-Clause    github.com/protomaps/basemaps
mapbox-gl-rtl-text.js   @mapbox/mapbox-gl-rtl-text 0.4.0 (Arabic)   BSD-2-Clause    rtl-text.LICENSE
fonts/                  Noto Sans glyphs (Latin, Arabic, punctuation, Arabic presentation forms)
                        from github.com/protomaps/basemaps-assets   SIL OFL 1.1     fonts/OFL.txt
sprites/                Protomaps "light" icons                     see sprites/LICENSE.md

The map data itself (maps/kuwait.pmtiles on the server, deploy/maps/update-map.sh) is OpenStreetMap
(ODbL 1.0): the map always shows "© OpenStreetMap".

Updating: the style (basemaps.js) must match the tiles' schema version (Protomaps basemap v4 tiles,
which build.protomaps.com produces). Source maps were removed from the files.
