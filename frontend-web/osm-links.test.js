import test from 'node:test';
import assert from 'node:assert/strict';
import { openStreetMapUrl } from './osm-links.js';

test('keeps an exact OpenStreetMap object link', () => {
  assert.equal(
    openStreetMapUrl({ mapUrl: 'https://www.openstreetmap.org/way/123' }),
    'https://www.openstreetmap.org/way/123',
  );
});

test('creates a centered OpenStreetMap link from coordinates', () => {
  assert.equal(
    openStreetMapUrl({ lat: 13.34, lon: 77.1, name: 'Tumakuru' }),
    'https://www.openstreetmap.org/?mlat=13.34&mlon=77.1#map=17/13.34/77.1',
  );
});

test('searches OpenStreetMap by place and trip location when coordinates are missing', () => {
  assert.equal(
    openStreetMapUrl({ name: 'Shivagange Hill', location: 'Tumakuru, India' }),
    'https://www.openstreetmap.org/search?query=Shivagange%20Hill%2C%20Tumakuru%2C%20India',
  );
});

test('does not create a map link without a place, coordinates, or valid OSM URL', () => {
  assert.equal(openStreetMapUrl({ mapUrl: 'javascript:alert(1)' }), null);
  assert.equal(openStreetMapUrl({ lat: 91, lon: 0 }), null);
  assert.equal(openStreetMapUrl({}), null);
});
