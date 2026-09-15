export function candidateInvitationUrl(sessionRoute, origin) {
  return new URL(sessionRoute, `${origin}/`).href;
}

export async function copyInvitation(input) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(input.value);
      return true;
    }
  } catch {
    // HTTP or browser permissions may prevent use of the Clipboard API.
  }

  // Keep the visible link selected for manual copying if the legacy API fails.
  input.focus();
  input.select();
  input.setSelectionRange(0, input.value.length);
  try {
    return document.execCommand?.('copy') === true;
  } catch {
    return false;
  }
}
