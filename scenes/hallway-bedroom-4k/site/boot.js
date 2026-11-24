import * as THREE from "three";
import * as Spark from "@sparkjsdev/spark";

window.THREE = THREE;
window.Spark = Spark;

const version = new URL(import.meta.url).search.slice(1);
const scripts = ["nav.js", "poi.js", "poi_ui.js", "poi_editor.js", "main.js"];

function load(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = version ? src + "?" + version : src;
    el.onload = resolve;
    el.onerror = () => reject(new Error("Could not load " + src));
    document.body.appendChild(el);
  });
}

scripts.reduce((chain, src) => chain.then(() => load(src)), Promise.resolve()).catch((e) => {
  const err = document.getElementById("err");
  if (err) { err.hidden = false; err.textContent = e.message; }
});
