import { Link } from 'react-router'

import { CenteredMessage } from '@/components/CenteredMessage'
import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <CenteredMessage title="Page not found">
      <Button variant="outline" asChild>
        <Link to="/">Go home</Link>
      </Button>
    </CenteredMessage>
  )
}
