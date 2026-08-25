"use client";

import { useState } from "react";
import StudyRoomLobby from "@/components/study-room/StudyRoomLobby";
import StudyRoomView from "@/components/study-room/StudyRoomView";
import type { StudyRoom } from "@/lib/api";

export default function StudyRoomPage() {
  const [selectedRoom, setSelectedRoom] =
    useState<StudyRoom | null>(null);

  if (selectedRoom !== null) {
    return (
      <StudyRoomView
        room={selectedRoom}
        onRoomDeleted={() => setSelectedRoom(null)}
      />
    );
  }

  return (
    <StudyRoomLobby
      onRoomSelected={setSelectedRoom}
    />
  );
}