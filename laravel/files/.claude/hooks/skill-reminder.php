<?php

declare(strict_types=1);

/**
 * PreToolUse hook for Edit|Write|MultiEdit. Tells the agent which project skills to load
 * before it edits a file, until the session transcript shows the skill was loaded.
 */
$skillsByPattern = [
    '#^Modules/[^/]+/(?!tests/).+\.php$#' => ['module-architecture', 'laravel-best-practices'],
    '#^(tests/|Modules/[^/]+/tests/).+\.php$#' => ['pest-testing', 'testing-best-practices'],
    '#^resources/js/.+\.(tsx|ts|jsx)$#' => ['inertia-react-development'],
];

$input = json_decode((string) stream_get_contents(STDIN), true);
if (!is_array($input)) {
    exit(0);
}

$filePath = (string) ($input['tool_input']['file_path'] ?? '');
$projectDir = mb_rtrim((string) (getenv('CLAUDE_PROJECT_DIR') ?: ($input['cwd'] ?? '')), '/').'/';
$relativePath = (string) preg_replace(
    '#^(.*/)?\.claude/worktrees/[^/]+/#',
    '',
    str_starts_with($filePath, $projectDir) ? mb_substr($filePath, mb_strlen($projectDir)) : $filePath,
);

$requiredSkills = [];
foreach ($skillsByPattern as $pattern => $skills) {
    if (preg_match($pattern, $relativePath) === 1) {
        $requiredSkills = [...$requiredSkills, ...$skills];
    }
}

if ($requiredSkills === []) {
    exit(0);
}

$transcriptPath = (string) ($input['transcript_path'] ?? '');
$transcript = $transcriptPath !== '' && is_readable($transcriptPath) ? (string) file_get_contents($transcriptPath) : '';

$missingSkills = array_values(array_filter(
    array_unique($requiredSkills),
    static fn (string $skill): bool => preg_match(
        '#"name":"Skill","input":\{"skill":"'.preg_quote($skill, '#').'"|<command-name>/'.preg_quote($skill, '#').'</command-name>#',
        $transcript,
    ) !== 1,
));

if ($missingSkills === []) {
    exit(0);
}

echo json_encode([
    'hookSpecificOutput' => [
        'hookEventName' => 'PreToolUse',
        'additionalContext' => 'Project rule: load the '.implode(', ', $missingSkills)
            .' skill(s) with the Skill tool before you edit '.$relativePath
            .'. Follow them, and re-check this edit against them.',
    ],
], JSON_UNESCAPED_SLASHES);
