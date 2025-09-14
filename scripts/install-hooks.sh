#!/bin/bash
echo "Installing pre-push hook..."
cp scripts/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
echo "Hook installed! Master branch is now protected locally."