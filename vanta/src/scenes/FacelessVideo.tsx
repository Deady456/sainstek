import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig, Audio, staticFile, OffthreadVideo, Sequence } from "remotion";
import React from "react";

// The props structure passed from assemble_vanta.py via --props
export interface FacelessVideoProps {
  title?: string;
  voice_audio?: string;
  broll?: string[];
  words?: { word: string; start: number; end: number }[];
  durationInSeconds?: number;
}

export const FacelessVideo: React.FC<FacelessVideoProps> = ({
  title = "Default Title",
  voice_audio,
  broll = [],
  words = [],
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  
  const currentTime = frame / fps;

  // Find which word is currently active based on time in seconds
  const activeCaptionIndex = words.findIndex(
    (caption) => currentTime >= caption.start && currentTime <= caption.end
  );

  // Group words into chunks (max 3 words per screen)
  const CHUNK_SIZE = 3;
  const chunks = [];
  for (let i = 0; i < words.length; i += CHUNK_SIZE) {
    chunks.push(words.slice(i, i + CHUNK_SIZE));
  }

  // Find which chunk we should display now
  const activeChunkIndex = activeCaptionIndex >= 0 
    ? Math.floor(activeCaptionIndex / CHUNK_SIZE)
    : -1;
  const activeChunk = chunks[activeChunkIndex] || [];

  // Simple b-roll logic: divide total duration equally among b-rolls
  const numBroll = broll.length > 0 ? broll.length : 1;
  const framesPerBroll = Math.ceil(durationInFrames / numBroll);

  return (
    <AbsoluteFill style={{ backgroundColor: "#111122" }}>
      
      {/* Inject Font */}
      <style>
        {`
          @import url('https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,800;0,900;1,800&family=Bangers&display=swap');
          
          .hook-text {
            background: linear-gradient(90deg, #FF007F 0%, #FFD700 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            -webkit-text-stroke: 0px; /* Disable stroke when using background-clip */
            filter: drop-shadow(0px 8px 15px rgba(0,0,0,0.8));
          }
        `}
      </style>

      {/* Voiceover */}
      {voice_audio && <Audio src={staticFile(voice_audio)} />}

      {/* B-roll Backgrounds (100% Brightness) */}
      {broll.map((vid, index) => (
        <Sequence
          key={index}
          from={index * framesPerBroll}
          durationInFrames={framesPerBroll}
        >
          <OffthreadVideo 
            src={staticFile(vid)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        </Sequence>
      ))}

      {/* Fallback Gradient if no B-roll */}
      {broll.length === 0 && (
        <AbsoluteFill
          style={{
            background: "radial-gradient(circle, rgba(255,255,255,0.1) 0%, rgba(0,0,0,0.8) 100%)",
          }}
        />
      )}

      {/* Subtle Gradient overlay ONLY at the bottom/center for text readability */}
      <AbsoluteFill
        style={{
          background: "linear-gradient(to top, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 40%, rgba(0,0,0,0) 60%)",
        }}
      />

      {/* Foreground Container */}
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          padding: 60,
        }}
      >
        {/* Title Hook - Only shows for the first 2 seconds */}
        {currentTime < 2 && title && (
          <div
            style={{
              position: "absolute",
              top: 300,
              fontSize: 85,
              fontWeight: 900,
              fontFamily: "'Montserrat', sans-serif",
              color: "white",
              backgroundColor: "#CC0000", // Red Pill Box
              padding: "20px 40px",
              borderRadius: "50px", // Pill shape
              textTransform: "uppercase",
              letterSpacing: 3,
              textAlign: "center",
              lineHeight: 1.1,
              boxShadow: "0px 10px 20px rgba(0,0,0,0.6)",
              transform: `scale(${spring({ fps, frame, config: { damping: 15 } })}) rotate(-2deg)`,
            }}
          >
            {title}
          </div>
        )}

        {/* Animated Captions (Premium Chunked View) */}
        <div
          style={{
            position: "absolute",
            bottom: 350,
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "18px",
            width: "80%",
            textAlign: "center",
          }}
        >
          {activeChunk.map((caption, index) => {
            // Re-calculate the global index to compare with activeCaptionIndex
            const globalIndex = activeChunkIndex * CHUNK_SIZE + index;
            const isActive = globalIndex === activeCaptionIndex;
            const hasPassed = globalIndex < activeCaptionIndex;
            
            // Convert start time to frame for spring animation
            const startFrame = Math.round(caption.start * fps);
            
            // Pop animation when word becomes active
            const scale = isActive
              ? spring({ fps, frame: frame - startFrame, config: { damping: 14, mass: 0.8 } })
              : 1;

            return (
              <span
                key={index}
                style={{
                  fontSize: 70,
                  fontWeight: 900,
                  fontFamily: "'Montserrat', sans-serif",
                  color: isActive ? "#FFD700" : "#FFFFFF",
                  backgroundColor: "rgba(0, 0, 0, 0.75)",
                  padding: "10px 25px",
                  borderRadius: "40px",
                  margin: "6px",
                  transform: `scale(${scale})`,
                  boxShadow: isActive ? "0px 0px 30px rgba(255, 215, 0, 0.6)" : "0px 10px 20px rgba(0,0,0,0.8)",
                  transition: "all 0.1s ease-out",
                  display: "inline-block",
                  lineHeight: 1.2,
                }}
              >
                {caption.word}
              </span>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
