import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import {
  interpretPresentation,
  WEB_RENDERER_CAPABILITIES,
} from './presentation-adapter.mjs';

const fixturePath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../tests/fixtures/presentation-research-v1.json',
);
const representativeContract = JSON.parse(
  await readFile(fixturePath, 'utf8'),
);

test('web adapter interprets the shared research contract semantically', () => {
  const result = interpretPresentation(representativeContract);
  assert.equal(result.kind, 'contract');
  assert.deepEqual(result.contract.content_hierarchy, ['summary', 'sources']);
  assert.equal(result.contract.components[1].items[0].title, 'Example research source');
});

test('web adapter explicitly falls back when required primitives are unsupported', () => {
  const unsupported = structuredClone(representativeContract);
  unsupported.renderer_requirements.required_components.push('map.render');
  const result = interpretPresentation(unsupported);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.text, 'I found one observed source.');
});

test('web adapter rejects data references outside the declared contract scope', () => {
  const invalid = structuredClone(representativeContract);
  invalid.components[1].items[0].data_ref = 'execution:another-user:artifact:0';
  const result = interpretPresentation(invalid);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.reason, 'Unauthorized data reference.');
});

test('web adapter falls back rather than rendering interactions without read permission', () => {
  const invalid = structuredClone(representativeContract);
  invalid.interactions[0].required_permissions = ['email:send'];
  const result = interpretPresentation(invalid);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.reason, 'Unsupported presentation interaction.');
});

test('web adapter explicitly falls back for a newer contract version', () => {
  const newer = structuredClone(representativeContract);
  newer.contract_version = '2.0';
  const result = interpretPresentation(newer);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.reason, 'Unsupported contract version.');
});

test('a renderer with a smaller feature set falls back without mutating the contract', () => {
  const original = structuredClone(representativeContract);
  const textOnlyRenderer = {
    ...WEB_RENDERER_CAPABILITIES,
    components: ['conversation.markdown'],
    modalities: ['text'],
  };
  const result = interpretPresentation(original, textOnlyRenderer);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.text, original.fallback.text);
  assert.deepEqual(original, representativeContract);
});

test('web renderer rejects non-public sources even when their scheme is HTTPS', () => {
  const invalid = structuredClone(representativeContract);
  invalid.components[1].items[0].url = 'https://private.local/research';
  const result = interpretPresentation(invalid);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.reason, 'Unsupported source reference.');
});

test('web renderer accepts validated user-provided point-map semantics', () => {
  const mapContract = structuredClone(representativeContract);
  const coordinateRef = 'execution:fixture-execution:coordinate';
  mapContract.content_hierarchy = ['summary', 'map'];
  mapContract.components[1] = {
    id: 'map',
    type: 'geospatial.point_map',
    title: 'Map of user-provided coordinates',
    items: [{
      data_ref: coordinateRef,
      latitude: 47.6062,
      longitude: -122.3321,
      label: '47.60620, -122.33210',
      units: {
        latitude: 'degrees_north',
        longitude: 'degrees_east',
      },
      location_type: 'user_provided',
    }],
  };
  mapContract.renderer_requirements.required_components = [
    'conversation.markdown',
    'geospatial.point_map',
  ];
  mapContract.renderer_requirements.required_modalities = ['text', 'map'];
  mapContract.modalities = ['text', 'map'];
  mapContract.data_refs = [{
    id: coordinateRef,
    kind: 'user_provided_coordinates',
  }];
  mapContract.interactions = [];
  mapContract.source_provenance = [{
    data_ref: coordinateRef,
    source_type: 'user_provided_coordinates',
    observed_at: '2026-10-09T13:30:00+00:00',
  }];

  const result = interpretPresentation(mapContract);
  assert.equal(result.kind, 'contract');
  assert.equal(result.contract.components[1].items[0].latitude, 47.6062);

  const noMapRenderer = {
    ...WEB_RENDERER_CAPABILITIES,
    components: ['conversation.markdown'],
    modalities: ['text'],
  };
  const fallback = interpretPresentation(mapContract, noMapRenderer);
  assert.equal(fallback.kind, 'fallback');
  assert.equal(fallback.text, mapContract.fallback.text);
});

test('web renderer rejects map coordinates outside geographic bounds', () => {
  const invalid = structuredClone(representativeContract);
  const coordinateRef = 'execution:fixture-execution:coordinate';
  invalid.content_hierarchy = ['summary', 'map'];
  invalid.components[1] = {
    id: 'map',
    type: 'geospatial.point_map',
    title: 'Map',
    items: [{
      data_ref: coordinateRef,
      latitude: 100,
      longitude: -122,
      label: 'invalid',
      units: {
        latitude: 'degrees_north',
        longitude: 'degrees_east',
      },
      location_type: 'user_provided',
    }],
  };
  invalid.renderer_requirements.required_components = [
    'conversation.markdown',
    'geospatial.point_map',
  ];
  invalid.renderer_requirements.required_modalities = ['text', 'map'];
  invalid.modalities = ['text', 'map'];
  invalid.data_refs = [{ id: coordinateRef, kind: 'user_provided_coordinates' }];
  invalid.interactions = [];
  invalid.source_provenance = [{
    data_ref: coordinateRef,
    source_type: 'user_provided_coordinates',
    observed_at: '2026-10-09T13:30:00+00:00',
  }];

  const result = interpretPresentation(invalid);
  assert.equal(result.kind, 'fallback');
  assert.equal(result.reason, 'Unsupported map coordinate.');
});
