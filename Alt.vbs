' Lancador do Alt sem janela de console.
' Clique duas vezes neste arquivo para deixar o Alt ativo em segundo plano.
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

pasta = fso.GetParentFolderName(WScript.ScriptFullName)
alt   = pasta & "\alt.py"

' Se o Python nao estiver em C:\Python314, o pythonw do PATH resolve.
pythonw = "C:\Python314\pythonw.exe"
If Not fso.FileExists(pythonw) Then pythonw = "pythonw.exe"

shell.CurrentDirectory = pasta
shell.Run """" & pythonw & """ """ & alt & """", 0, False
