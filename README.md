# Gradient Signs Website

Public landing page for gradientsigns.com

## Files
- `index.html` — main landing page

## Hosting
GitHub Pages + custom domain (gradientsigns.com)

## Private project gallery

`gallery/index.html` is a password prompt. The gallery page and its photos are encrypted with [StatiCrypt](https://github.com/robinmoisson/staticrypt) (AES-256-CBC). The key is derived from the password with PBKDF2-SHA-256. Decrypting happens in the browser. There is no server and no password stored in this repo.

The photos are embedded in the HTML before encryption, so the published file has no image URLs and no readable photo bytes. View-source and the network panel show ciphertext until the password is entered.

### Add or replace photos

1. Install the build tool: `npm install`
2. Put JPEG, PNG, WebP, or GIF files in `gallery-src/`. That folder is gitignored. Do not commit the photos.
3. Name files in the order they should appear. The filename becomes the caption. `01-storefront-channel-letters.jpg` is shown as “Storefront Channel Letters”. A leading `sample-` is kept as “Sample — …”.
4. Rebuild. The password is read from the environment and is never written to disk by the script:

```bash
GALLERY_PASSWORD='a long password you keep elsewhere' ./scripts/build-gallery
```

5. Commit the new `gallery/index.html`. If `.staticrypt.json` changed, commit that too. It holds the public salt, not the password.

The password page has an optional “Remember me on this browser” checkbox. Checked, the browser stores a salted hash for 30 days. Unchecked, a reload locks the gallery again.

Use a long password (at least 14 characters). To change it, run the script again with the new `GALLERY_PASSWORD`. People who had checked “Remember me” will need to enter the new password.
