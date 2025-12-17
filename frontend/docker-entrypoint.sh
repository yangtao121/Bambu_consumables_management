#!/bin/sh
set -e

# Generate a runtime-config file so prebuilt images can be configured without rebuild.
# Note: Next.js inlines NEXT_PUBLIC_* at build time, so we must avoid relying on it for client code.
JS_VALUE="$(node -p 'JSON.stringify(process.env.NEXT_PUBLIC_API_BASE_URL || "")')"

mkdir -p /app/public
cat > /app/public/runtime-config.js <<EOF
// Generated at container startup.
window.__API_BASE_URL__=${JS_VALUE};
EOF

exec "$@"

