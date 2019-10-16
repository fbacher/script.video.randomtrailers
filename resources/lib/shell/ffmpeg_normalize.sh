#!/bin/sh
set -x
(
file="${1}" 
outFile="${2}"
filename=$(basename -- "$file")
extension="${filename##*.}"
filename="${filename%.*}"
outDirectoryPath=$(dirname "$outFile")
outfilename=$(basename -- "$outFile")
outExtension="$(outfilename##.*)"
newOutFileName="$outDirectoryPath"/compand_"${outfilename}""${outExtension}"
echo $newOutFileName
useCompand="false"
useNormalize="true"
#passLogFile=$(mktemp /tmp/random_trailer_XXXXX)
#exec 3>"${passLogFile}"
#rm "{$passLogFile}"

passLogFile=`mktemp`

if "${useCompand}" -eq "true" 
  then
	ffmpeg -i "${file}" -pass 1 -passlogfile "${passLogFile}" -c:v copy -filter_complex:a \
	 "compand=attacks=0:points=-80/-900|-45/-15|-27/-9|0/-7|20/-7:gain=1" -y /dev/null
	ffmpeg -i "${file}" -pass 2 -passlogfile "${passLogFile}" -c:v copy -filter_complex:a \
	 "compand=attacks=0:points=-80/-900|-45/-15|-27/-9|0/-7|20/-7:gain=1" -y "${newOutFileName}"
fi
if  ${useNormalize} == "true" 
 then
#	ffmpeg -i "${file}" -pass 1 -passlogfile "${passLogFile}" -filter:a loudnorm=dual_mono=true -y /dev/null
#	ffmpeg -i "${file}" -pass 2 -passlogfile "${passLogFile}" -filter:a loudnorm=dual_mono=true -y "${outFile}"
	ffmpeg -i "${file}" -pass 1 -passlogfile "${passLogFile}" -c:v copy -filter:a loudnorm -f null 
	ffmpeg -i "${file}" -pass 2 -passlogfile "${passLogFile}" -c:v copy -filter:a loudnorm -y "${outFile}"
	rm -f ${passLogFile}
fi 
) >/tmp/normalize.log 2>&1
