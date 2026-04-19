import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import Library from "./pages/Library";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Library />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
