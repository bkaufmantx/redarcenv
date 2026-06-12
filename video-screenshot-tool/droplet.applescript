-- RedArc Video Tool — drag-drop droplet (portable)
-- Drop one or more MP4/MOV files on this app's icon. It runs the transcription
-- pipeline in Terminal so you can watch progress, then opens the output folder.
--
-- Path-relative: the app finds its sibling scripts by resolving its own
-- location at runtime, so it works wherever the folder is unzipped — no
-- hardcoded path.

on run
	display dialog "Drag one or more video files onto this app's icon to process them." buttons {"OK"} default button "OK" with title "RedArc Video Tool"
end run

on open theFiles
	-- This .app lives inside the tool folder; its parent dir is where the
	-- scripts + venv are. Resolve it from `path to me` at run time.
	set appPosix to POSIX path of (path to me)
	set fileArgs to ""
	repeat with f in theFiles
		set fileArgs to fileArgs & " " & quoted form of POSIX path of f
	end repeat
	set cmd to "APP=" & (quoted form of appPosix) & "; DIR=\"$(cd \"$(dirname \"${APP%/}\")\" && pwd)\"; cd \"$DIR\" && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH && ./venv/bin/python ./process_video.py" & fileArgs & " && open ./output"
	tell application "Terminal"
		activate
		do script cmd
	end tell
end open
