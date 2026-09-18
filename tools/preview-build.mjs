/** Development helper: build the preview bundle (see rollup.preview.mjs for why this exists). */
import { rollup } from 'rollup';
import config from './rollup.preview.mjs';

const bundle = await rollup(config);
const { output } = await bundle.write(config.output);
console.log('preview built:', output.map(o => o.fileName).join(', '));
await bundle.close();
