import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// Static adapter: `npm run dev` runs locally now; `npm run build` later
		// produces a fully static site (e.g. for GitHub Pages) with no rework.
		adapter: adapter({
			fallback: 'index.html'
		})
	}
};

export default config;
