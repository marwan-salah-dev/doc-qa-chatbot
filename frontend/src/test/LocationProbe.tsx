import { useLocation } from 'react-router'

/** Shows the current path, so a test can check where something navigated to. */
export function LocationProbe() {
  return <p data-testid="location">{useLocation().pathname}</p>
}
