function getWeather() {
  const city = document.getElementById("city").value;
  if (!city) return alert("Please enter a city");

  fetch(`/weather?city=${encodeURIComponent(city)}`)
    .then((res) => res.json())
    .then((data) => {
      if (data.error) {
        document.getElementById("result").innerText = data.error;
      } else {
        const cacheNote = data.cached ? " (cached)" : "";
        document.getElementById("result").innerText =
          `Temperature in ${data.city} is ${data.temperature}°C\nWeather: ${data.description}${cacheNote}`;
      }
    })
    .catch((err) => {
      console.error(err);
      document.getElementById("result").innerText = "Request failed. Try again.";
    });
}
