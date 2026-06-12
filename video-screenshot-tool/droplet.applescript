-- RedArc Video Tool — drag-drop droplet
-- Drop one or more MP4 (or MOV) files on this app's icon. It runs the
-- screenshot + transcript pipeline in Terminal so you can watch progress,
-- then opens the output folder.

property scriptDir : "/Users/briankaufman/Desktop/SAR Master Folder/RedArc/video-screenshot-tool"

on run
	display dialog "Drag one or more video files onto this app's icon to process them." buttons {"OK"} default button "OK" with title "RedArc Video Tool"
end run

on open theFiles
	set fileArgs to ""
	repeat with f in theFiles
		set fileArgs to fileArgs & " " & quoted form of POSIX path of f
	end repeat
	set cmd to "cd " & quoted form of scriptDir & " && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH && ./venv/bin/python ./process_video.py" & fileArgs & " && open ./output"
	tell application "Terminal"
		activate
		do script cmd
	end tell
end open
