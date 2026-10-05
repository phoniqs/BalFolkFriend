/* tslint:disable */
/* eslint-disable */
/**
*/
export function init_panic_hook(): void;
/**
*/
export class FolkFriendWASM {
  free(): void;
/**
*/
  constructor();
/**
* @returns {string}
*/
  version(): string;
/**
* @param {any} js_value
*/
  load_index_from_json_obj(js_value: any): void;
/**
* @param {number} sample_rate
*/
  set_sample_rate(sample_rate: number): void;
/**
*/
  feed_entire_pcm_signal(): void;
/**
* @returns {number}
*/
  alloc_single_pcm_window(): number;
/**
* @param {number} ptr
* @returns {Float32Array}
*/
  get_allocated_pcm_window(ptr: number): Float32Array;
/**
* @param {number} ptr
*/
  feed_single_pcm_window(ptr: number): void;
/**
*/
  flush_pcm_buffer(): void;
/**
* @returns {string}
*/
  transcribe_pcm_buffer(): string;
/**
* @param {string} contour_string
* @returns {string}
*/
  run_transcription_query(contour_string: string): string;
/**
* @param {string} query
* @returns {string}
*/
  run_name_query(query: string): string;
/**
* @param {string} contour_string
* @returns {string}
*/
  contour_to_abc(contour_string: string): string;
/**
* @param {string} tune_id
* @returns {string}
*/
  settings_from_tune_id(tune_id: string): string;
/**
* @param {string} tune_id
* @returns {string}
*/
  aliases_from_tune_id(tune_id: string): string;
}
