' 隱藏視窗啟動器：讓排程執行 run.bat 時不跳出黑色主控台視窗。
'
' 為什麼需要這個：排程若以「僅在使用者登入時執行」的方式直接跑 run.bat，
' 每天會彈出一個主控台視窗並停留十幾分鐘。視窗一旦被關掉，Python 會收到
' CTRL_CLOSE_EVENT 而中止，工作排程器回報 0xC000013A，當天的更新就沒完成。
' 用 WScript.Shell 以視窗樣式 0（隱藏）啟動，就沒有可被關閉的視窗。
'
' 第三個參數 True 代表等待 run.bat 結束才返回，好讓排程器的「上次結果」
' 與執行時限反映真正的管線狀態，而不是啟動器本身。

Option Explicit
Dim shell, fso, scriptDir, exitCode, target

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

If WScript.Arguments.Count > 0 Then
    target = WScript.Arguments(0)
Else
    target = "run.bat"
End If

exitCode = shell.Run("""" & scriptDir & "\" & target & """", 0, True)

WScript.Quit exitCode
