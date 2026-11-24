// Compatibility shims that let `yarn lint` run. Import this file first in
// eslint.config.js: it must run before any plugin is loaded. See .ai/rules/js.md.
import { createRequire } from 'node:module';

import { SourceCode } from 'eslint';

const require = createRequire(import.meta.filename);

// 1. typescript-eslint 8 supports TypeScript <6.1 only, while the repo pins
// typescript@^7 for tsc and the build (TS 7 has no JS API). Put the TS 6 JS API
// (`eslint-typescript6`, an alias of @typescript/typescript6) into the
// CommonJS cache in place of `typescript`, so typescript-eslint gets TS 6.
// This affects the lint process only; tsc and the build keep TS 7.
const typescriptPath = require.resolve('typescript');

require.cache[typescriptPath] = {
    id: typescriptPath,
    filename: typescriptPath,
    loaded: true,
    exports: require('eslint-typescript6'),
};

// 2. ESLint 10 removed SourceCode#getTokenOrCommentBefore/After, which
// eslint-plugin-import 2.32 (`import/order`) still calls. Restore them with
// their documented replacement.
SourceCode.prototype.getTokenOrCommentBefore ??= function (node, skip = 0) {
    return this.getTokenBefore(node, { includeComments: true, skip });
};

SourceCode.prototype.getTokenOrCommentAfter ??= function (node, skip = 0) {
    return this.getTokenAfter(node, { includeComments: true, skip });
};
