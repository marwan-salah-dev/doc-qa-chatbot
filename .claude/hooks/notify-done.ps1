# Stop hook: show a Windows toast when Claude Code finishes a turn.
# Uses the built-in WinRT toast API (no modules to install). Never fails the hook.
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml(@"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>Claude Code finished</text>
      <text>doc-qa-chatbot is waiting for you.</text>
    </binding>
  </visual>
</toast>
"@)

    # Windows PowerShell's own app ID, so the toast shows without registering a new app.
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
} catch {
    # A missing toast must never block or fail Claude Code.
}
exit 0
