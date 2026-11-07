# A throwaway local window for checks/agentdesktop_smoke.py. It contains no user data.
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.Text = "Hey Harry agent-desktop smoke"
$form.Width = 420; $form.Height = 330
$form.StartPosition = "Manual"; $form.Left = 60; $form.Top = 60

$status = New-Object System.Windows.Forms.Label
$status.Text = "idle"; $status.Name = "statusLabel"; $status.Left = 20; $status.Top = 20; $status.Width = 360
$form.Controls.Add($status)

$hello = New-Object System.Windows.Forms.Button
$hello.Text = "Say Hello"; $hello.Name = "helloButton"; $hello.Left = 20; $hello.Top = 50; $hello.Width = 120
$hello.Add_Click({ $status.Text = "hello pressed" })
$form.Controls.Add($hello)

# A button whose press opens a modal question, so its UI Automation Invoke doesn't return till the question closes.
$ask = New-Object System.Windows.Forms.Button
$ask.Text = "Ask First"; $ask.Name = "askButton"; $ask.Left = 150; $ask.Top = 50; $ask.Width = 120
$ask.Add_Click({
    $status.Text = "asking"
    [void][System.Windows.Forms.MessageBox]::Show($form, "Are you sure?", "Hey Harry smoke question")
    $status.Text = "asked"
})
$form.Controls.Add($ask)

$check = New-Object System.Windows.Forms.CheckBox
$check.Text = "Night light"; $check.Name = "nightCheck"; $check.Left = 20; $check.Top = 90; $check.Width = 160
$form.Controls.Add($check)

$plain = New-Object System.Windows.Forms.TextBox
$plain.Name = "plainBox"; $plain.AccessibleName = "Message"; $plain.Left = 20; $plain.Top = 130; $plain.Width = 360
$form.Controls.Add($plain)

$secret = New-Object System.Windows.Forms.TextBox
$secret.Name = "secretBox"; $secret.AccessibleName = "Password"; $secret.UseSystemPasswordChar = $true
$secret.Left = 20; $secret.Top = 170; $secret.Width = 360; $secret.Text = "not-a-real-password"
$form.Controls.Add($secret)

$delete = New-Object System.Windows.Forms.Button
$delete.Text = "Delete"; $delete.Name = "deleteButton"; $delete.Left = 20; $delete.Top = 210; $delete.Width = 120
$delete.Add_Click({ $status.Text = "delete pressed" })
$form.Controls.Add($delete)

$quit = New-Object System.Windows.Forms.Button
$quit.Text = "Quit"; $quit.Name = "quitButton"; $quit.Left = 260; $quit.Top = 210; $quit.Width = 120
$quit.Add_Click({ $form.Close() })
$form.Controls.Add($quit)

[System.Windows.Forms.Application]::Run($form)
