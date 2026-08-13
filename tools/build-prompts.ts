import {
  buildAll,
  checkGenerated,
  PromptBundleError,
  writeAll,
} from './prompt-bundler';

function usage(): never {
  console.error(
    'Usage: bun run tools/build-prompts.ts [--check|--phase <phase>]',
  );
  process.exit(2);
}

if (import.meta.main) {
  const root = process.cwd();
  const args = process.argv.slice(2);

  try {
    if (args.includes('--check')) {
      if (args.length !== 1) usage();

      const errors = checkGenerated(root);

      if (errors.length > 0) {
        for (const error of errors) {
          console.error(`✗ ${error}`);
        }
        process.exit(1);
      }

      console.log('✓ Generated prompt bundles are up to date');
    } else if (args[0] === '--phase') {
      const phase = args[1];

      if (!phase || args.length !== 2) {
        usage();
      }

      // --phase es una operación de rebuild completo, no un build parcial.
      // Primero resolvemos el árbol en memoria y validamos que la fase exista.
      // Sólo después escribimos cualquier artefacto.
      const built = buildAll(root);

      if (!Object.prototype.hasOwnProperty.call(built.manifest.phases, phase)) {
        throw new PromptBundleError(`unknown phase: ${phase}`);
      }

      const manifest = writeAll(root);

      console.log(`✓ Generated ${manifest.phases[phase].path}`);
      console.log(
        `✓ Synchronized prompt-manifest.json and ${Object.keys(manifest.phases).length} phase bundles`,
      );
    } else if (args.length === 0) {
      const manifest = writeAll(root);

      console.log('✓ Generated prompts/generated/tony-orchestrator.md');
      console.log(
        `✓ Generated ${Object.keys(manifest.phases).length} phase bundles`,
      );
      console.log('✓ Generated prompts/generated/prompt-manifest.json');
    } else {
      usage();
    }
  } catch (error) {
    const message =
      error instanceof PromptBundleError || error instanceof Error
        ? error.message
        : String(error);

    console.error(`✗ ${message}`);
    process.exit(1);
  }
}
