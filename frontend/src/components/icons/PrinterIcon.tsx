import * as React from "react";
const SVGComponent = (props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    xmlnsXlink="http://www.w3.org/1999/xlink"
    x="0px"
    y="0px"
    width="24px"
    height="24px"
    viewBox="0 0 24 24"
    style={{
      enableBackground: "new 0 0 24 24",
    }}
    xmlSpace="preserve"
    {...props}
  >
    <style type="text/css">
      {
        "\n\t.st0{fill:#FFFFFF;}\n\t.st1{fill:none;stroke:#000000;stroke-width:2;stroke-miterlimit:10;}\n"
      }
    </style>
    <defs />
    <g>
      <path
        className="st0"
        d="M3.2,23C2,23,1,22,1,20.8V3.2C1,2,2,1,3.2,1h17.5C22,1,23,2,23,3.2v17.5c0,1.2-1,2.2-2.2,2.2H3.2z"
      />
      <path d="M20.8,2C21.4,2,22,2.6,22,3.2v17.5c0,0.7-0.6,1.2-1.2,1.2H3.2C2.6,22,2,21.4,2,20.8V3.2C2,2.6,2.6,2,3.2,2H20.8 M20.8,0 H3.2C1.4,0,0,1.4,0,3.2v17.5C0,22.6,1.4,24,3.2,24h17.5c1.8,0,3.2-1.4,3.2-3.2V3.2C24,1.4,22.6,0,20.8,0L20.8,0z" />
    </g>
    <g>
      <path
        className="st0"
        d="M7,7C6.5,7,6,6.5,6,6V2c0-0.6,0.5-1,1-1h10c0.6,0,1,0.5,1,1v4c0,0.6-0.5,1-1,1H7z"
      />
      <path d="M17,2L17,2v4L7,6l0-4H17 M17,0H7C5.9,0,5,0.9,5,2v4c0,1.1,0.9,2,2,2h10c1.1,0,2-0.9,2-2V2C19,0.9,18.1,0,17,0L17,0z" />
    </g>
    <path d="M9,8c1,1,2,2,3,3c1-1,2-2,3-3C13,8,11,8,9,8z" />
    <path
      className="st1"
      d="M17.6,20H6.4C5.6,20,5,19.4,5,18.6v-3.2C5,14.6,5.6,14,6.4,14h11.2c0.8,0,1.4,0.6,1.4,1.4v3.2 C19,19.4,18.4,20,17.6,20z"
    />
  </svg>
);
export default SVGComponent;
