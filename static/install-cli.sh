#!/bin/bash
set -euo pipefail

REPO="jottit/jottit"
BIN_NAME="jottit"

echo "Installing Jottit CLI..."

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH" && exit 1 ;;
esac

VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name"' | cut -d'"' -f4)
if [ -z "$VERSION" ]; then
    echo "Failed to determine latest version."
    exit 1
fi

URL="https://github.com/$REPO/releases/download/$VERSION/${BIN_NAME}-${OS}-${ARCH}"
echo "Downloading $BIN_NAME $VERSION for $OS/$ARCH..."

TMP=$(mktemp)
curl -fsSL "$URL" -o "$TMP"
chmod +x "$TMP"

INSTALL_DIR="/usr/local/bin"
if [ -w "$INSTALL_DIR" ]; then
    mv "$TMP" "$INSTALL_DIR/$BIN_NAME"
elif command -v sudo >/dev/null 2>&1; then
    sudo mv "$TMP" "$INSTALL_DIR/$BIN_NAME"
else
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
    mv "$TMP" "$INSTALL_DIR/$BIN_NAME"
    if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
        echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "${HOME}/.profile"
        echo "Added $INSTALL_DIR to PATH in ~/.profile. Restart your shell or run:"
        echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    fi
fi

echo "Installed $BIN_NAME $VERSION to $INSTALL_DIR/$BIN_NAME"
"$INSTALL_DIR/$BIN_NAME" --version
