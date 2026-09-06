#!/usr/bin/env ruby
# Local-only assembly of the existing deck, synthetic narration and timed captions.
require 'json'
require 'open3'
require 'fileutils'
require 'digest'

root = File.expand_path('..', __dir__)
build = File.join(root, '.artifacts/pitch/kokoro-interim')
FileUtils.mkdir_p(build)
output = File.join(root, 'submission/planrace-interim-pitch.mp4')
abort 'Output already exists; inspect it before choosing a new output.' if File.exist?(output)
scenes = JSON.parse(File.read(File.join(root, 'submission/pitch-narration.json')))
deck = File.join(root, 'submission/PlanRace_Checkpoint_Pitch.pptx')
abort 'Unexpected source deck' unless Digest::SHA256.file(deck).hexdigest == 'd95c48cf8cd2dcb202a7157b779c62211d11e5a7d31d000bd7e1599237ac0e50'
def run(*args)
  out, err, result = Open3.capture3(*args)
  abort "Failed: #{args.first}\n#{err[-3000..] || err}" unless result.success?
  out
end
def timestamp(seconds)
  ms = (seconds * 1000).round
  format('%02d:%02d:%02d,%03d', ms / 3600000, ms / 60000 % 60, ms / 1000 % 60, ms % 1000)
end
offset = 0.0
captions = []
clips = []
timings = []
scenes.each do |scene|
  slide = scene.fetch('slide')
  frame = File.join(root, ".artifacts/pitch/rendered-v2/slide-#{slide}.png")
  abort "Missing rendered slide #{slide}" unless File.file?(frame)
  audio_files = []
  scene_start = offset
  scene.fetch('sentences').each_with_index do |sentence, index|
    audio = File.join(build, "slide-#{slide}-#{index}.wav")
    abort "Missing Kokoro audio #{audio}; run synthesize_pitch.py first" unless File.file?(audio)
    duration = JSON.parse(run('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', audio)).fetch('format').fetch('duration').to_f
    lines = sentence.scan(/.{1,68}(?:\s|$)|\S+$/).map(&:strip).join("\n")
    captions << "#{captions.length + 1}\n#{timestamp(offset)} --> #{timestamp(offset + duration)}\n#{lines}\n"
    offset += duration
    audio_files << audio
  end
  duration = offset - scene_start
  listing = File.join(build, "audio-#{slide}.txt")
  File.write(listing, audio_files.map { |p| "file '#{p}'" }.join("\n") + "\n")
  clip = File.join(build, "slide-#{slide}.mp4")
  run('ffmpeg', '-nostdin', '-v', 'error', '-loop', '1', '-framerate', '10', '-i', frame,
      '-f', 'concat', '-safe', '0', '-i', listing, '-t', duration.to_s,
      '-vf', 'scale=1920:1080,setsar=1', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage',
      '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '1', clip)
  clips << clip
  clip_duration = JSON.parse(run('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', clip)).fetch('format').fetch('duration').to_f
  offset = scene_start + clip_duration
  timings << {slide:slide,start:scene_start,end:offset,source_sha256:Digest::SHA256.file(frame).hexdigest}
  puts "Rendered slide #{slide}: #{duration.round(2)} seconds"
  STDOUT.flush
end
srt = File.join(root, 'submission/planrace-interim-pitch.srt')
File.write(srt, captions.join("\n"))
File.write(File.join(root, 'submission/planrace-interim-pitch.vtt'), "WEBVTT\n\n" + captions.join("\n").gsub(/(\d{2}:\d{2}:\d{2}),(\d{3})/, '\1.\2'))
listing = File.join(build, 'video.txt')
File.write(listing, clips.map { |p| "file '#{p}'" }.join("\n") + "\n")
run('ffmpeg', '-nostdin', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', listing,
    '-i', srt, '-map', '0:v', '-map', '0:a', '-map', '1:0', '-c', 'copy', '-c:s', 'mov_text',
    '-c:a', 'aac', '-b:a', '160k', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '44100',
    '-metadata:s:s:0', 'language=eng', '-metadata:s:a:0', 'language=eng',
    '-metadata', 'title=PlanRace interim pitch: localnet evidence, testnet pending',
    '-disposition:s:0', 'default', '-movflags', '+faststart', output)
metadata = JSON.parse(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', output))
File.write(File.join(build, 'assembly.json'), JSON.pretty_generate({
  source_deck_sha256:Digest::SHA256.file(deck).hexdigest,
  synthetic_voice:'Kokoro-82M v1.0 af_heart, speed 1.0, Apache-2.0 model',
  captions:'Sentence boundaries use measured source audio durations; embedded mov_text and sidecar SRT.',
  limitations:['Interim localnet pitch, not a testnet demo.', 'Full perceptual audio/video review remains required.'],
  timeline:timings, metadata:metadata, output_sha256:Digest::SHA256.file(output).hexdigest
}) + "\n")
puts "Created #{output}"
