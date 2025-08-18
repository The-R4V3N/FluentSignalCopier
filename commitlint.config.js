// commitlint.config.js
module.exports = {
    extends: ["@commitlint/config-conventional"],
    rules: {
        "body-max-line-length": [2, "always", 100],
        "footer-max-line-length": [2, "always", 100],
        "subject-case": [2, "never", ["sentence-case", "start-case", "pascal-case", "upper-case"]],
        "type-enum": [
            2,
            "always",
            [
                "feat",     // new feature
                "fix",      // bug fix
                "docs",     // documentation only
                "style",    // formatting, missing semicolons, no code change
                "refactor", // code change that isn’t fix or feat
                "perf",     // performance improvement
                "test",     // adding/updating tests
                "build",    // build system / dependencies
                "ci",       // CI/CD config
                "chore",    // maintenance
                "revert"    // revert commit
            ]
        ]
    }
};
// This configuration file is used to enforce commit message conventions